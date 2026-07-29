"""OpenAI-compatible structured API support for semantic QA scoring."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import Any, Dict, Mapping, Optional


ALLOWED_SCORES = (0.0, 0.25, 0.5, 0.75, 1.0)
API_MODES = ("responses", "chat-completions")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_evaluation_input(
    *,
    question: Any,
    expected_answer: Any,
    source_evidence: Any,
    candidate_response: Any,
) -> str:
    """Serialize all untrusted fields as one canonical JSON data object."""
    return canonical_json(
        {
            "QUESTION": str(question or ""),
            "EXPECTED_ANSWER": str(expected_answer or ""),
            "SOURCE_EVIDENCE": str(source_evidence or ""),
            "CANDIDATE_RESPONSE": str(candidate_response or ""),
        }
    )


class SemanticAPIError(RuntimeError):
    """Base error for request, response, or semantic-score failures."""


class SemanticHTTPError(SemanticAPIError):
    def __init__(self, *, status: int, body: str, retry_after: Optional[float] = None):
        super().__init__(f"HTTP {status}: {body[:1000]}")
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.status in {408, 409, 425, 429} or 500 <= self.status <= 599


@dataclass(frozen=True)
class SemanticAPIResult:
    score: float
    response_id: Optional[str]
    response_model: Optional[str]
    request_hash: str
    raw_response: Mapping[str, Any]


def _retry_after_seconds(headers: Message) -> Optional[float]:
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


def _response_text(payload: Mapping[str, Any], api_mode: str) -> str:
    if api_mode == "responses":
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        texts = []
        for item in payload.get("output", []) or []:
            if not isinstance(item, Mapping) or item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, Mapping):
                    continue
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    texts.append(content["text"])
                elif content.get("type") == "refusal":
                    raise SemanticAPIError(f"Judge refused: {content.get('refusal', '')}")
        if texts:
            return "".join(texts)
        raise SemanticAPIError("Responses API result contains no output text")

    choices = payload.get("choices", []) or []
    if not choices or not isinstance(choices[0], Mapping):
        raise SemanticAPIError("Chat Completions result contains no choices")
    message = choices[0].get("message", {}) or {}
    if message.get("refusal"):
        raise SemanticAPIError(f"Judge refused: {message['refusal']}")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise SemanticAPIError("Chat Completions result contains no text content")
    return content


def parse_semantic_score(payload: Mapping[str, Any], *, api_mode: str) -> float:
    try:
        parsed = json.loads(_response_text(payload, api_mode))
    except json.JSONDecodeError as exc:
        raise SemanticAPIError(f"Structured output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"semantic_score"}:
        raise SemanticAPIError("Structured output must contain only semantic_score")
    value = parsed["semantic_score"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticAPIError("semantic_score must be numeric")
    score = float(value)
    if score not in ALLOWED_SCORES:
        raise SemanticAPIError(f"semantic_score must be one of {list(ALLOWED_SCORES)}")
    return score


class OpenAISemanticClient:
    """Minimal client for OpenAI Responses or Chat Completions structured output."""

    def __init__(
        self,
        *,
        model: str,
        system_prompt: str,
        schema: Mapping[str, Any],
        api_key: str = "",
        api_mode: str = "chat-completions",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        temperature: Optional[float] = 0.0,
        reasoning_effort: Optional[str] = None,
        max_output_tokens: int = 1024,
    ):
        if api_mode not in API_MODES:
            raise ValueError(f"api_mode must be one of {API_MODES}")
        if not model:
            raise ValueError("model must not be empty")
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.schema = {key: value for key, value in schema.items() if key != "$schema"}
        self.api_mode = api_mode
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    def request_payload(self, user_input: str) -> Dict[str, Any]:
        if self.api_mode == "responses":
            payload: Dict[str, Any] = {
                "model": self.model,
                "instructions": self.system_prompt,
                "input": [{"role": "user", "content": [{"type": "input_text", "text": user_input}]}],
                "max_output_tokens": self.max_output_tokens,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "semantic_score_v1",
                        "strict": True,
                        "schema": self.schema,
                    }
                },
            }
            if self.reasoning_effort is not None:
                payload["reasoning"] = {"effort": self.reasoning_effort}
        else:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_input},
                ],
                "max_completion_tokens": self.max_output_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "semantic_score_v1",
                        "strict": True,
                        "schema": self.schema,
                    },
                },
            }
            if self.reasoning_effort is not None:
                payload["reasoning_effort"] = self.reasoning_effort
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return payload

    def evaluate(self, user_input: str) -> SemanticAPIResult:
        payload = self.request_payload(user_input)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = "responses" if self.api_mode == "responses" else "chat/completions"
        request = urllib.request.Request(
            f"{self.base_url}/{endpoint}",
            data=canonical_json(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SemanticHTTPError(
                status=exc.code,
                body=exc.read().decode("utf-8", errors="replace"),
                retry_after=_retry_after_seconds(exc.headers),
            ) from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SemanticAPIError(f"API request or response failed: {exc}") from exc
        if not isinstance(raw, dict):
            raise SemanticAPIError("API response must be a JSON object")
        return SemanticAPIResult(
            score=parse_semantic_score(raw, api_mode=self.api_mode),
            response_id=str(raw["id"]) if raw.get("id") is not None else None,
            response_model=str(raw["model"]) if raw.get("model") is not None else None,
            request_hash=sha256_json(payload),
            raw_response=raw,
        )


def retry_delay_seconds(
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
    retry_after: Optional[float] = None,
) -> float:
    if retry_after is not None:
        return min(max(retry_after, 0.0), max_seconds)
    return min(base_seconds * (2 ** max(attempt - 1, 0)), max_seconds)


def sleep_before_retry(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
