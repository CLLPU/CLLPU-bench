#!/usr/bin/env python3
"""Extract Step-3 knowledge cards from Wikipedia topic-pair content with an LLM API."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests


PROMPT_VERSION = "step3_pairability_v2"

RELATION_HINTS = {
    "franchise": {
        "multi_instance_priority": [
            "major_characters",
            "fictional_organizations",
            "signature_terms",
            "important_locations",
            "major_vehicles_or_artifacts",
        ],
        "shared_core_relations": [
            "creator",
            "first_release_year",
            "original_medium",
            "major_characters",
            "fictional_organizations",
            "signature_terms",
        ],
        "singleton_support": [
            "creator",
            "first_release_year",
            "original_medium",
        ],
    },
    "space mission": {
        "multi_instance_priority": [
            "crew_member",
            "spacecraft",
            "mission_objective",
            "equipment_or_payload",
            "historical_first",
        ],
        "shared_core_relations": [
            "mission_date",
            "country",
            "space_agency",
            "crew_member",
            "spacecraft",
            "launch_site",
            "historical_first",
        ],
        "singleton_support": [
            "mission_date",
            "country",
            "space_agency",
            "launch_site",
        ],
    },
    "person": {
        "multi_instance_priority": [
            "notable_work",
            "occupation",
            "artistic_field",
            "patron_or_affiliation",
            "major_invention_or_project",
        ],
        "shared_core_relations": [
            "birth_date",
            "birth_place",
            "death_date",
            "occupation",
            "notable_work",
            "artistic_field",
        ],
        "singleton_support": [
            "birth_date",
            "birth_place",
            "death_date",
        ],
    },
    "medical substance": {
        "multi_instance_priority": [
            "medical_use",
            "related_disease_or_target_condition",
            "mechanism_or_biological_role",
            "notable_risk_or_side_effect",
            "source_or_production",
            "chemical_or_structural_class",
            "route_of_administration",
            "administration_or_delivery",
            "formulation_or_analogue",
            "scientific_first_or_structure",
        ],
        "shared_core_relations": [
            "substance_type",
            "medical_use",
            "mechanism_or_biological_role",
            "source_or_production",
            "related_disease_or_target_condition",
            "notable_risk_or_side_effect",
            "chemical_or_structural_class",
            "route_of_administration",
            "administration_or_delivery",
            "formulation_or_analogue",
            "scientific_first_or_structure",
        ],
        "singleton_support": [
            "substance_type",
            "discoverer",
            "discovery_year",
        ],
        "short_answer_examples": [
            "drug/formulation names such as penicillin G, penicillin V, Humalog, NovoRapid, Apidra, Lantus, Levemir",
            "routes or delivery devices such as intramuscular injection, subcutaneous injections, inhaled insulin, insulin pump",
            "conditions or risks such as diabetes, type 1 diabetes, hypoglycemia, diarrhoea, rash, anaphylaxis",
            "sources or structures such as Penicillium moulds, P. chrysogenum, insulin gene, 51 amino acids",
        ],
    },
    "mythology system": {
        "multi_instance_priority": [
            "major_deities",
            "central_creatures",
            "mythic_realm",
            "cosmology_term",
            "source_text_or_tradition",
        ],
        "shared_core_relations": [
            "chief_deity",
            "major_deities",
            "cosmology_term",
            "mythic_realm",
            "source_text_or_tradition",
            "central_creatures",
        ],
        "singleton_support": [
            "chief_deity",
        ],
    },
    "company": {
        "multi_instance_priority": [
            "major_acquisition",
            "major_brand",
            "flagship_product",
            "product_line",
            "subsidiary",
            "market_segment",
        ],
        "shared_core_relations": [
            "founded_year",
            "founder",
            "headquarters",
            "flagship_product",
            "industry",
            "major_acquisition",
        ],
        "singleton_support": [
            "founded_year",
            "founder",
            "headquarters",
            "industry",
        ],
    },
}

RELATION_HINTS.update(
    {
        "near-Earth object": {
            "multi_instance_priority": [
                "discovery",
                "orbital_parameter",
                "close_approach",
                "impact_risk_assessment",
                "physical_characteristic",
            ],
            "shared_core_relations": [
                "discovery_date",
                "discoverer_or_survey",
                "object_class",
                "closest_approach_date",
                "estimated_diameter",
                "orbital_period",
                "impact_risk_assessment",
            ],
            "singleton_support": ["discovery_date", "object_class"],
        },
        "near-Earth asteroid": {
            "multi_instance_priority": [
                "discovery",
                "orbital_parameter",
                "close_approach",
                "impact_risk_assessment",
                "physical_characteristic",
            ],
            "shared_core_relations": [
                "discovery_date",
                "discoverer_or_survey",
                "object_class",
                "closest_approach_date",
                "estimated_diameter",
                "orbital_period",
                "impact_risk_assessment",
            ],
            "singleton_support": ["discovery_date", "object_class"],
        },
        "comet": {
            "multi_instance_priority": [
                "discovery",
                "orbital_parameter",
                "perihelion",
                "observational_characteristic",
                "classification",
            ],
            "shared_core_relations": [
                "discovery_date",
                "discoverer_or_survey",
                "perihelion_date",
                "perihelion_distance",
                "orbital_period",
                "closest_approach_date",
                "classification",
            ],
            "singleton_support": ["discovery_date", "classification"],
        },
        "dinosaur genus": {
            "multi_instance_priority": [
                "taxonomy",
                "fossil_material",
                "geological_formation",
                "discovery_or_naming",
                "anatomical_feature",
            ],
            "shared_core_relations": [
                "clade_or_family",
                "type_species",
                "geological_formation",
                "country_or_region",
                "geologic_period",
                "named_by",
                "specimen_material",
            ],
            "singleton_support": ["type_species", "geologic_period"],
        },
        "pterosaur genus": {
            "multi_instance_priority": [
                "taxonomy",
                "fossil_material",
                "geological_formation",
                "discovery_or_naming",
                "anatomical_feature",
            ],
            "shared_core_relations": [
                "clade_or_family",
                "type_species",
                "geological_formation",
                "country_or_region",
                "geologic_period",
                "named_by",
                "specimen_material",
            ],
            "singleton_support": ["type_species", "geologic_period"],
        },
        "disease outbreak": {
            "multi_instance_priority": [
                "location",
                "case_count",
                "death_count",
                "pathogen_or_disease",
                "response_measure",
            ],
            "shared_core_relations": [
                "disease",
                "start_date",
                "location",
                "confirmed_cases",
                "deaths",
                "health_agency",
                "response_measure",
            ],
            "singleton_support": ["disease", "start_date"],
        },
        "hurricane": {
            "multi_instance_priority": [
                "meteorological_record",
                "landfall",
                "impact",
                "damage_or_casualty",
                "affected_area",
            ],
            "shared_core_relations": [
                "storm_category",
                "formation_date",
                "dissipation_date",
                "peak_wind_speed",
                "minimum_pressure",
                "landfall_location",
                "damage",
                "fatalities",
            ],
            "singleton_support": ["formation_date", "storm_category"],
        },
        "typhoon": {
            "multi_instance_priority": [
                "meteorological_record",
                "landfall",
                "impact",
                "damage_or_casualty",
                "affected_area",
            ],
            "shared_core_relations": [
                "storm_category",
                "formation_date",
                "dissipation_date",
                "peak_wind_speed",
                "minimum_pressure",
                "landfall_location",
                "damage",
                "fatalities",
            ],
            "singleton_support": ["formation_date", "storm_category"],
        },
        "tropical cyclone": {
            "multi_instance_priority": [
                "meteorological_record",
                "landfall",
                "impact",
                "damage_or_casualty",
                "affected_area",
            ],
            "shared_core_relations": [
                "storm_category",
                "formation_date",
                "dissipation_date",
                "peak_wind_speed",
                "minimum_pressure",
                "landfall_location",
                "damage",
                "fatalities",
            ],
            "singleton_support": ["formation_date", "storm_category"],
        },
        "flood event": {
            "multi_instance_priority": [
                "affected_area",
                "cause",
                "impact",
                "damage_or_casualty",
                "response_measure",
            ],
            "shared_core_relations": [
                "event_date",
                "country_or_region",
                "affected_area",
                "cause",
                "fatalities",
                "damage",
                "response_measure",
            ],
            "singleton_support": ["event_date", "country_or_region"],
        },
        "wildfire": {
            "multi_instance_priority": [
                "location",
                "timeline",
                "impact",
                "damage_or_casualty",
                "containment_or_response",
            ],
            "shared_core_relations": [
                "start_date",
                "location",
                "area_burned",
                "structures_destroyed",
                "fatalities",
                "cause",
                "containment_date",
            ],
            "singleton_support": ["start_date", "location"],
        },
        "earthquake": {
            "multi_instance_priority": [
                "seismological_record",
                "location",
                "impact",
                "damage_or_casualty",
                "response_measure",
            ],
            "shared_core_relations": [
                "date",
                "magnitude",
                "depth",
                "epicenter",
                "affected_area",
                "fatalities",
                "damage",
            ],
            "singleton_support": ["date", "magnitude"],
        },
        "power outage": {
            "multi_instance_priority": [
                "affected_area",
                "cause",
                "impact",
                "duration",
                "response_measure",
            ],
            "shared_core_relations": [
                "date",
                "affected_country_or_region",
                "cause",
                "people_affected",
                "duration",
                "infrastructure_affected",
            ],
            "singleton_support": ["date", "affected_country_or_region"],
        },
        "aviation accident": {
            "multi_instance_priority": [
                "aircraft",
                "operator",
                "location",
                "casualty_count",
                "flight_detail",
            ],
            "shared_core_relations": [
                "date",
                "aircraft_type",
                "operator",
                "origin",
                "destination",
                "accident_location",
                "fatalities",
                "survivors",
            ],
            "singleton_support": ["date", "aircraft_type"],
        },
        "road incident": {
            "multi_instance_priority": [
                "location",
                "vehicle_or_structure",
                "casualty_count",
                "cause_or_trigger",
                "response_measure",
            ],
            "shared_core_relations": [
                "date",
                "location",
                "vehicle_type",
                "fatalities",
                "injuries",
                "cause",
                "infrastructure_involved",
            ],
            "singleton_support": ["date", "location"],
        },
        "bus crash": {
            "multi_instance_priority": [
                "location",
                "vehicle_or_structure",
                "casualty_count",
                "cause_or_trigger",
                "response_measure",
            ],
            "shared_core_relations": [
                "date",
                "location",
                "vehicle_type",
                "fatalities",
                "injuries",
                "cause",
                "operator_or_route",
            ],
            "singleton_support": ["date", "location"],
        },
        "land transport or infrastructure accident": {
            "multi_instance_priority": [
                "location",
                "vehicle_or_structure",
                "casualty_count",
                "cause_or_trigger",
                "response_measure",
            ],
            "shared_core_relations": [
                "date",
                "location",
                "transport_mode",
                "fatalities",
                "injuries",
                "cause",
                "infrastructure_involved",
            ],
            "singleton_support": ["date", "location"],
        },
        "federal election": {
            "multi_instance_priority": [
                "party_result",
                "leader",
                "seat_count",
                "vote_share",
                "government_formation",
            ],
            "shared_core_relations": [
                "election_date",
                "winning_party",
                "prime_minister_or_leader",
                "seats_won",
                "popular_vote",
                "turnout",
            ],
            "singleton_support": ["election_date", "winning_party"],
        },
        "general election": {
            "multi_instance_priority": [
                "party_result",
                "leader",
                "seat_count",
                "vote_share",
                "government_formation",
            ],
            "shared_core_relations": [
                "election_date",
                "winning_party",
                "prime_minister_or_leader",
                "seats_won",
                "popular_vote",
                "turnout",
            ],
            "singleton_support": ["election_date", "winning_party"],
        },
        "presidential election": {
            "multi_instance_priority": [
                "candidate_result",
                "party_affiliation",
                "vote_count",
                "vote_share",
                "round_or_runoff",
            ],
            "shared_core_relations": [
                "election_date",
                "winner",
                "runner_up",
                "party",
                "vote_share",
                "turnout",
                "runoff_date",
            ],
            "singleton_support": ["election_date", "winner"],
        },
        "award ceremony": {
            "multi_instance_priority": [
                "host",
                "venue",
                "award_winner",
                "nominee",
                "broadcast_or_producer",
            ],
            "shared_core_relations": [
                "ceremony_date",
                "venue",
                "host",
                "major_winner",
                "most_nominations",
                "network",
            ],
            "singleton_support": ["ceremony_date", "venue"],
        },
        "film festival": {
            "multi_instance_priority": [
                "award_winner",
                "screening",
                "jury_or_host",
                "venue",
                "opening_or_closing_film",
            ],
            "shared_core_relations": [
                "festival_date",
                "location",
                "top_prize_winner",
                "jury_president",
                "opening_film",
                "closing_film",
            ],
            "singleton_support": ["festival_date", "location"],
        },
        "music contest/festival": {
            "multi_instance_priority": [
                "performer",
                "song",
                "venue",
                "result",
                "host_or_broadcaster",
            ],
            "shared_core_relations": [
                "event_date",
                "venue",
                "host_city",
                "winner",
                "winning_song",
                "presenter_or_host",
            ],
            "singleton_support": ["event_date", "venue"],
        },
        "football tournament": {
            "multi_instance_priority": [
                "team_result",
                "venue",
                "match",
                "player_award",
                "host_country",
            ],
            "shared_core_relations": [
                "tournament_dates",
                "host_country",
                "winner",
                "runner_up",
                "venue",
                "top_scorer",
            ],
            "singleton_support": ["tournament_dates", "host_country"],
        },
        "film": {
            "multi_instance_priority": [
                "cast_member",
                "production_company",
                "release",
                "box_office",
                "director_or_writer",
            ],
            "shared_core_relations": [
                "release_date",
                "director",
                "cast_member",
                "production_company",
                "distributor",
                "box_office",
                "based_on",
            ],
            "singleton_support": ["release_date", "director"],
        },
        "smartphone": {
            "multi_instance_priority": [
                "hardware_spec",
                "display_spec",
                "camera_spec",
                "software",
                "release",
            ],
            "shared_core_relations": [
                "announcement_date",
                "release_date",
                "chipset",
                "display_size",
                "operating_system",
                "camera_feature",
                "storage_option",
            ],
            "singleton_support": ["announcement_date", "chipset"],
        },
        "smartphone series": {
            "multi_instance_priority": [
                "model",
                "hardware_spec",
                "display_spec",
                "camera_spec",
                "software",
            ],
            "shared_core_relations": [
                "announcement_date",
                "models",
                "chipset",
                "display_size",
                "operating_system",
                "camera_feature",
                "battery_capacity",
            ],
            "singleton_support": ["announcement_date", "models"],
        },
        "gaming handheld": {
            "multi_instance_priority": [
                "hardware_spec",
                "display_spec",
                "game_or_platform_support",
                "release",
                "storage_or_battery",
            ],
            "shared_core_relations": [
                "announcement_date",
                "release_date",
                "processor",
                "display_size",
                "storage",
                "battery",
                "platform",
            ],
            "singleton_support": ["announcement_date", "release_date"],
        },
        "electric SUV": {
            "multi_instance_priority": [
                "battery_or_range",
                "powertrain",
                "dimensions",
                "release_or_sales",
                "manufacturer",
            ],
            "shared_core_relations": [
                "manufacturer",
                "announcement_date",
                "battery_capacity",
                "range",
                "powertrain",
                "price",
                "production_site",
            ],
            "singleton_support": ["manufacturer", "announcement_date"],
        },
        "new-energy SUV": {
            "multi_instance_priority": [
                "battery_or_range",
                "powertrain",
                "dimensions",
                "release_or_sales",
                "manufacturer",
            ],
            "shared_core_relations": [
                "manufacturer",
                "announcement_date",
                "battery_capacity",
                "range",
                "powertrain",
                "price",
                "production_site",
            ],
            "singleton_support": ["manufacturer", "announcement_date"],
        },
        "mixed reality headset": {
            "multi_instance_priority": [
                "hardware_spec",
                "display_spec",
                "chipset",
                "software",
                "release",
            ],
            "shared_core_relations": [
                "announcement_date",
                "release_date",
                "processor",
                "display_resolution",
                "operating_system",
                "price",
                "tracking_feature",
            ],
            "singleton_support": ["announcement_date", "processor"],
        },
        "system-on-chip": {
            "multi_instance_priority": [
                "cpu_spec",
                "gpu_spec",
                "neural_engine",
                "manufacturing_process",
                "device_usage",
            ],
            "shared_core_relations": [
                "announcement_date",
                "process_node",
                "cpu_core_count",
                "gpu_core_count",
                "neural_engine",
                "memory_support",
                "used_in_device",
            ],
            "singleton_support": ["announcement_date", "process_node"],
        },
        "AI model": {
            "multi_instance_priority": [
                "developer",
                "release",
                "capability",
                "product_integration",
                "benchmark_or_context_window",
            ],
            "shared_core_relations": [
                "developer",
                "release_date",
                "model_family",
                "context_window",
                "modality",
                "product_integration",
                "license_or_access",
            ],
            "singleton_support": ["developer", "release_date"],
        },
        "AI model family release": {
            "multi_instance_priority": [
                "developer",
                "release",
                "capability",
                "model_variant",
                "product_integration",
            ],
            "shared_core_relations": [
                "developer",
                "release_date",
                "model_variant",
                "context_window",
                "modality",
                "product_integration",
                "license_or_access",
            ],
            "singleton_support": ["developer", "release_date"],
        },
    }
)

BLUEPRINT_SYSTEM_PROMPT = """You design high-pairability extraction plans for a cross-lingual unlearning benchmark.

Return JSON only.
Your goal is to maximize the number of valid relation-matched card pairs available in Step 4.
Prefer shared relation families that can produce multiple distinct atomic facts on both sides.
Do not extract cards yet. First design a relation blueprint with quotas.
"""

EXTRACTION_SYSTEM_PROMPT = """You extract high-quality knowledge cards for a cross-lingual unlearning benchmark.

Return JSON only.
Every card must be an atomic_fact with direct evidence from the provided page content.
Do not invent facts, do not merge multiple facts into one card, and do not create target/neighbor pairs.
Follow the provided shared-relation blueprint and favor multi-instance relation families that increase future pairing yield.
Copy source_span as closely as possible from the source page content.
Keep answers short, concrete, and easy to evaluate automatically.
Avoid duplicate cards, duplicate answers under the same relation, and trivia with weak Step-4 pairing value.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config/llm_api.env",
        help="Local env-style config file for LLM API settings.",
    )
    parser.add_argument(
        "--input",
        default="data/wiki_page_content.json",
        help="Input topic-pair wiki content JSON.",
    )
    parser.add_argument(
        "--output",
        default="data/knowledge_cards.json",
        help="Output knowledge card inventory JSON.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/step3_knowledge_card_cache",
        help="Directory for per-pair raw and normalized cache files.",
    )
    parser.add_argument(
        "--pair-id",
        action="append",
        dest="pair_ids",
        help="Optional pair_id to process. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=None,
        help="Process at most N pairs after filtering.",
    )
    parser.add_argument(
        "--max-cards-per-topic",
        type=int,
        default=30,
        help="Ask the model to extract up to this many cards per topic.",
    )
    parser.add_argument(
        "--min-multi-instance-cards-per-topic",
        type=int,
        default=18,
        help="Target minimum number of cards per topic from multi-instance relation families.",
    )
    parser.add_argument(
        "--api-base",
        default="",
        help="Base URL for the OpenAI-compatible API.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for the OpenAI-compatible API.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model name for extraction.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignore any existing output file and rebuild from scratch.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force fresh API calls even if cached per-pair outputs exist.",
    )
    parser.add_argument(
        "--merge-output",
        action="store_true",
        help=(
            "When updating an existing output, merge newly generated cards with "
            "existing cards for the same pair instead of replacing the pair."
        ),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_env_config_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def split_api_keys(raw_value: str) -> List[str]:
    if not raw_value:
        return []
    return [part.strip() for part in re.split(r"[\n,]+", raw_value) if part.strip()]


def resolve_api_keys(*candidates: str) -> List[str]:
    keys: List[str] = []
    seen = set()
    for candidate in candidates:
        for key in split_api_keys(candidate or ""):
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 10:
        return "***"
    return f"{api_key[:6]}...{api_key[-4:]}"


def resolve_runtime_settings(args: argparse.Namespace) -> None:
    config_values = load_env_config_file(Path(args.config))
    args.api_base = (
        args.api_base
        or os.environ.get("STEP3_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("API_BASE")
        or config_values.get("STEP3_API_BASE")
        or config_values.get("OPENAI_BASE_URL")
        or config_values.get("API_BASE")
        or ""
    )
    args.api_keys = resolve_api_keys(
        args.api_key,
        os.environ.get("STEP3_API_KEYS", ""),
        os.environ.get("OPENAI_API_KEYS", ""),
        os.environ.get("API_KEYS", ""),
        os.environ.get("STEP3_API_KEY", ""),
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("API_KEY", ""),
        config_values.get("STEP3_API_KEYS", ""),
        config_values.get("OPENAI_API_KEYS", ""),
        config_values.get("API_KEYS", ""),
        config_values.get("STEP3_API_KEY", ""),
        config_values.get("OPENAI_API_KEY", ""),
        config_values.get("API_KEY", ""),
    )
    args.api_key = args.api_keys[0] if args.api_keys else ""
    args.model = (
        args.model
        or os.environ.get("STEP3_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL")
        or config_values.get("STEP3_MODEL")
        or config_values.get("OPENAI_MODEL")
        or config_values.get("MODEL")
        or "gemini-3.1-pro-preview-thinking"
    )


def ensure_api_args(args: argparse.Namespace) -> None:
    if not args.api_base:
        raise SystemExit("Missing API base. Use --api-base or set STEP3_API_BASE / OPENAI_BASE_URL / API_BASE.")
    if not getattr(args, "api_keys", None):
        raise SystemExit(
            "Missing API key. Use --api-key or set STEP3_API_KEY / STEP3_API_KEYS / OPENAI_API_KEY / OPENAI_API_KEYS / API_KEY / API_KEYS."
        )


def normalize_api_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def load_existing_output(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    return {item["pair_id"]: item for item in data.get("topic_pairs", [])}


def filter_pairs(topic_pairs: Iterable[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    selected = list(topic_pairs)
    if args.pair_ids:
        allowed = set(args.pair_ids)
        selected = [pair for pair in selected if pair.get("pair_id") in allowed]
    if args.max_pairs is not None:
        selected = selected[: args.max_pairs]
    return selected


def split_pair_topic_types(topic_type: str) -> Tuple[str, str]:
    left, right = topic_type.split(" vs ", 1)
    return left.strip(), right.strip()


def relation_profile_text(topic_type: str) -> str:
    profile = RELATION_HINTS.get(topic_type, {})
    multi_instance = ", ".join(profile.get("multi_instance_priority", []))
    shared_core = ", ".join(profile.get("shared_core_relations", []))
    singleton_support = ", ".join(profile.get("singleton_support", []))
    short_answer_examples = "; ".join(profile.get("short_answer_examples", []))
    return (
        f"Shared core relations: {shared_core or 'use the most pairable relations supported by the page'}\n"
        f"Multi-instance priority relations: {multi_instance or 'favor relations with multiple distinct answers'}\n"
        f"Singleton support relations: {singleton_support or 'use singleton relations only as supplemental support'}"
        + (
            f"\nShort-answer examples to prefer: {short_answer_examples}"
            if short_answer_examples
            else ""
        )
    )


def build_blueprint_prompt(
    pair: Dict[str, Any],
    max_cards_per_topic: int,
    min_multi_instance_cards_per_topic: int,
) -> str:
    target = pair["target"]
    neighbor = pair["neighbor"]
    target_type, neighbor_type = split_pair_topic_types(pair["topic_type"])
    target_profile = relation_profile_text(target_type)
    neighbor_profile = relation_profile_text(neighbor_type)

    return f"""Pair ID:
{pair["pair_id"]}

Pair topic type:
{pair["topic_type"]}

Target topic:
{target["topic_en"]}

Target topic type:
{target_type}

Target relation profile:
{target_profile}

Target Wikipedia page:
Title: {target["wiki_title"]}
URL: {target["wiki_url"]}
Content:
{target["page_content"]}

Neighbor topic:
{neighbor["topic_en"]}

Neighbor topic type:
{neighbor_type}

Neighbor relation profile:
{neighbor_profile}

Neighbor Wikipedia page:
Title: {neighbor["wiki_title"]}
URL: {neighbor["wiki_url"]}
Content:
{neighbor["page_content"]}

Task:
Design a shared-relation extraction blueprint that maximizes the number of valid relation-matched card pairs in Step 4.

Planning goals:
1. Plan for up to {max_cards_per_topic} cards for target and up to {max_cards_per_topic} cards for neighbor.
2. At least {min_multi_instance_cards_per_topic} planned cards per topic should come from multi-instance relation families when directly supported.
3. Prefer 8-12 shared relation families total.
4. Prioritize relation families that can yield 2-5 distinct cards on both sides.
5. Use singleton relations only as supplemental support.
6. Do not include relations that are unlikely to be directly supported by both pages.
7. Keep target and neighbor quotas balanced. For high-priority relation families, avoid planning many cards on one side unless the other side has comparable directly supported evidence.
8. The blueprint should support Step 4 with allow_card_reuse=false, so plan enough distinct target and neighbor cards for non-reused pairing.
9. Do not extract cards yet.

Return JSON only with this schema:
{{
  "pair_id": "{pair["pair_id"]}",
  "topic_type": "{pair["topic_type"]}",
  "target_total_card_goal": {max_cards_per_topic},
  "neighbor_total_card_goal": {max_cards_per_topic},
  "minimum_multi_instance_cards_per_topic": {min_multi_instance_cards_per_topic},
  "shared_relation_blueprint": [
    {{
      "relation_type": "...",
      "semantic_slot_family": "...",
      "answer_type": "...",
      "pairability_priority": "high | medium | low",
      "multi_instance_expected": true,
      "target_card_quota": 0,
      "neighbor_card_quota": 0,
      "target_support_summary": "...",
      "neighbor_support_summary": "...",
      "rationale": "..."
    }}
  ],
  "backup_relations": ["..."],
  "planning_notes": "..."
}}"""


def build_extraction_prompt(
    pair: Dict[str, Any],
    blueprint: Dict[str, Any],
    max_cards_per_topic: int,
    min_multi_instance_cards_per_topic: int,
) -> str:
    target = pair["target"]
    neighbor = pair["neighbor"]
    target_type, neighbor_type = split_pair_topic_types(pair["topic_type"])

    prompt = f"""Pair ID:
{pair["pair_id"]}

Pair topic type:
{pair["topic_type"]}

Target topic:
{target["topic_en"]}

Target topic type:
{target_type}

Target relation profile:
{relation_profile_text(target_type)}

Target Wikipedia page:
Title: {target["wiki_title"]}
URL: {target["wiki_url"]}
Content:
{target["page_content"]}

Neighbor topic:
{neighbor["topic_en"]}

Neighbor topic type:
{neighbor_type}

Neighbor relation profile:
{relation_profile_text(neighbor_type)}

Neighbor Wikipedia page:
Title: {neighbor["wiki_title"]}
URL: {neighbor["wiki_url"]}
Content:
{neighbor["page_content"]}

Approved shared-relation blueprint:
{json.dumps(blueprint, ensure_ascii=False, indent=2)}

Task:
Extract a high-pairability candidate pool of up to {max_cards_per_topic} knowledge cards for the target topic and up to {max_cards_per_topic} knowledge cards for the neighbor topic.

Requirements:
1. Each card must be one atomic_fact.
2. Each card must express exactly one core relation.
3. Follow the shared-relation blueprint closely and prioritize shared relation families with high pairability_priority.
4. Every card must include relation_type, semantic_slot, and answer_type.
5. Answers must be short, concrete, and easy to score.
6. fact_statement must be directly supported by source_span.
7. source_span should be copied as closely as possible from the page content.
8. Aim for at least {min_multi_instance_cards_per_topic} cards per topic from multi-instance relation families when directly supported.
9. Within the same relation_type, prefer multiple distinct answers rather than one generic singleton fact.
10. Avoid duplicate or near-duplicate cards:
   - no repeated answer under the same relation_type
   - no repeated fact_statement with only cosmetic wording changes
   - no low-value trivia if a more pairable relation family is available
11. Use singleton relations only as supplemental support to improve coverage.
12. Keep target and neighbor extraction balanced. If one side is shorter, continue searching that page for directly supported cards in the same high-priority relation families.
13. For each shared multi-instance relation, extract as many cards as possible from BOTH target and neighbor pages before moving to singleton relations.
14. The output should support Step 4 with allow_card_reuse=false; avoid extracting many cards for a relation on one side unless the other side has enough compatible cards.
15. Prefer source_span text that includes the exact answer string, because local normalization drops cards when the source span cannot be found and flags cards when the answer is absent.
16. If direct evidence allows, each of target.knowledge_cards and neighbor.knowledge_cards should contain at least 70 percent of the requested max card count after deduplication.
17. Keep answer values minimal: prefer a named entity, disease, route, drug/formulation, organism, place, date, or short term.
18. Do not put explanations, parenthetical rationales, causes, symptoms, or combined event summaries inside answer.
19. For answer, use text that appears verbatim in source_span whenever possible; avoid paraphrased answers that cannot be substring-matched.
20. Avoid answers longer than 6 English words unless the official name itself is longer.
21. Do not create target/neighbor pairs.
22. Return JSON only.

Output schema:
{{
  "pair_id": "{pair["pair_id"]}",
  "topic_type": "{pair["topic_type"]}",
  "target": {{
    "topic_role": "target",
    "topic_name": "{target["topic_en"]}",
    "topic_type": "{target_type}",
    "source_page": "{target["wiki_title"]}",
    "source_url": "{target["wiki_url"]}",
    "knowledge_cards": [
      {{
        "card_id": "...",
        "card_type": "atomic_fact",
        "relation_type": "...",
        "semantic_slot": "...",
        "fact_statement": "...",
        "answer": "...",
        "answer_type": "...",
        "section_title": "...",
        "source_span": "...",
        "aliases": ["..."],
        "knowledge_scope": "atomic",
        "eval_priority": "high"
      }}
    ]
  }},
  "neighbor": {{
    "topic_role": "neighbor",
    "topic_name": "{neighbor["topic_en"]}",
    "topic_type": "{neighbor_type}",
    "source_page": "{neighbor["wiki_title"]}",
    "source_url": "{neighbor["wiki_url"]}",
    "knowledge_cards": [
      {{
        "card_id": "...",
        "card_type": "atomic_fact",
        "relation_type": "...",
        "semantic_slot": "...",
        "fact_statement": "...",
        "answer": "...",
        "answer_type": "...",
        "section_title": "...",
        "source_span": "...",
        "aliases": ["..."],
        "knowledge_scope": "atomic",
        "eval_priority": "high"
      }}
    ]
  }}
}}"""
    return prompt


def call_chat_completion(
    session: requests.Session,
    api_base: str,
    api_keys: Sequence[str],
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    timeout: int,
) -> Dict[str, Any]:
    url = f"{normalize_api_base(api_base)}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    last_error: Optional[Exception] = None
    total_keys = len(api_keys)
    for attempt in range(1, 4):
        for key_index, api_key in enumerate(api_keys, start=1):
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            try:
                response = session.post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code >= 400 and "response_format" in response.text:
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = session.post(url, headers=headers, json=fallback_payload, timeout=timeout)
                response.raise_for_status()
                if attempt > 1 or key_index > 1:
                    log(
                        f"  API call succeeded with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}) on pass {attempt}."
                    )
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if key_index < total_keys:
                    log(
                        f"  API call failed with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}); trying next key: {exc}"
                    )
                else:
                    log(
                        f"  API call failed on pass {attempt}/3 with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}): {exc}"
                    )
        if attempt == 3:
            break
        sleep_seconds = min(5 * attempt, 15)
        log(f"  Exhausted {total_keys} configured API keys on pass {attempt}/3, retrying in {sleep_seconds}s.")
        time.sleep(sleep_seconds)
    assert last_error is not None
    raise last_error


def extract_message_text(response_json: Dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        raise ValueError("Model response did not contain any choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("Unsupported message content format in model response.")


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_model_json_response(response_json: Dict[str, Any]) -> Dict[str, Any]:
    response_text = extract_message_text(response_json)
    return extract_json_object(response_text)


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value or "card"


def ensure_pair_card_ids(pair: Dict[str, Any]) -> Dict[str, Any]:
    """Make model-provided card IDs globally stable across the inventory."""
    pair_id = slugify(pair["pair_id"])
    seen: Set[str] = set()
    for role in ("target", "neighbor"):
        prefix = f"{pair_id}_{role}_"
        for index, card in enumerate(pair.get(role, {}).get("knowledge_cards", []), start=1):
            base_id = slugify(card.get("card_id") or f"card_{index:03d}")
            if not base_id.startswith(prefix):
                base_id = f"{prefix}{base_id}"

            card_id = base_id
            suffix = 2
            while card_id in seen:
                card_id = f"{base_id}_{suffix:02d}"
                suffix += 1
            seen.add(card_id)
            card["card_id"] = card_id
    return pair


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_aliases(aliases: Any, fallback_topic_name: str) -> List[str]:
    if isinstance(aliases, list):
        cleaned = [normalize_whitespace(item) for item in aliases if normalize_whitespace(item)]
        if cleaned:
            return list(dict.fromkeys(cleaned))
    return [normalize_whitespace(fallback_topic_name)]


def span_supported(page_content: str, source_span: str) -> bool:
    normalized_page = normalize_whitespace(page_content)
    normalized_span = normalize_whitespace(source_span)
    if not normalized_span:
        return False
    return normalized_span in normalized_page


def answer_supported(answer: str, source_span: str) -> bool:
    normalized_answer = normalize_whitespace(answer).lower()
    normalized_span = normalize_whitespace(source_span).lower()
    if not normalized_answer:
        return False
    return normalized_answer in normalized_span


def card_signature(card: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        card["relation_type"],
        slugify(card["answer_type"]),
        normalize_whitespace(card["answer"]).lower(),
    )


def merge_topic_cards(existing_pair: Dict[str, Any], new_pair: Dict[str, Any]) -> Dict[str, Any]:
    merged_pair = copy.deepcopy(new_pair)
    for role in ("target", "neighbor"):
        seen: Set[Tuple[str, str]] = set()
        merged_cards: List[Dict[str, Any]] = []
        for source_pair in (existing_pair, new_pair):
            for card in source_pair.get(role, {}).get("knowledge_cards", []):
                signature = (
                    card.get("relation_type", ""),
                    normalize_whitespace(card.get("answer", "")).lower(),
                )
                if signature in seen:
                    continue
                seen.add(signature)
                merged_cards.append(card)
        merged_pair[role]["knowledge_cards"] = merged_cards
    return merged_pair


def normalize_card(
    card: Dict[str, Any],
    topic_name: str,
    page_content: str,
    existing_ids: set,
    sequence: int,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    relation_type = slugify(normalize_whitespace(card.get("relation_type", "")))
    semantic_slot = normalize_whitespace(card.get("semantic_slot", ""))
    fact_statement = normalize_whitespace(card.get("fact_statement", ""))
    answer = normalize_whitespace(card.get("answer", ""))
    answer_type = slugify(normalize_whitespace(card.get("answer_type", "")))
    section_title = normalize_whitespace(card.get("section_title", ""))
    source_span = normalize_whitespace(card.get("source_span", ""))
    eval_priority = normalize_whitespace(card.get("eval_priority", "medium")).lower()
    eval_priority = eval_priority if eval_priority in {"high", "medium", "low"} else "medium"

    required_values = {
        "relation_type": relation_type,
        "semantic_slot": semantic_slot,
        "fact_statement": fact_statement,
        "answer": answer,
        "answer_type": answer_type,
        "section_title": section_title,
        "source_span": source_span,
    }
    missing = [name for name, value in required_values.items() if not value]
    if missing:
        return None, [f"missing fields: {', '.join(missing)}"]

    if not span_supported(page_content, source_span):
        return None, ["source_span not found in page_content after whitespace normalization"]
    if not answer_supported(answer, source_span):
        warnings.append("answer not directly found in source_span")

    raw_card_id = normalize_whitespace(card.get("card_id", ""))
    if raw_card_id:
        card_id = slugify(raw_card_id)
    else:
        card_id = f"{slugify(topic_name)}_{relation_type}_{sequence:03d}"
    while card_id in existing_ids:
        sequence += 1
        card_id = f"{slugify(topic_name)}_{relation_type}_{sequence:03d}"
    existing_ids.add(card_id)

    normalized = {
        "card_id": card_id,
        "card_type": "atomic_fact",
        "relation_type": relation_type,
        "semantic_slot": semantic_slot,
        "fact_statement": fact_statement,
        "answer": answer,
        "answer_type": answer_type,
        "section_title": section_title,
        "source_span": source_span,
        "aliases": normalize_aliases(card.get("aliases"), topic_name),
        "knowledge_scope": "atomic",
        "eval_priority": eval_priority,
    }
    return normalized, warnings


def normalize_topic_payload(
    pair_id: str,
    side_name: str,
    source_topic: Dict[str, Any],
    generated_topic: Dict[str, Any],
    default_topic_type: str,
) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []

    normalized_topic = {
        "topic_role": side_name,
        "topic_name": source_topic["topic_en"],
        "topic_type": generated_topic.get("topic_type") or default_topic_type,
        "source_page": source_topic["wiki_title"],
        "source_url": source_topic["wiki_url"],
        "knowledge_cards": [],
    }

    existing_ids: set = set()
    seen_signatures: set = set()
    seen_fact_statements: set = set()
    cards = generated_topic.get("knowledge_cards") or []
    for index, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            warnings.append(f"{pair_id}/{side_name}: skipped non-object card")
            continue
        normalized_card, card_warnings = normalize_card(
            card=card,
            topic_name=source_topic["topic_en"],
            page_content=source_topic["page_content"],
            existing_ids=existing_ids,
            sequence=index,
        )
        for warning in card_warnings:
            warnings.append(f"{pair_id}/{side_name}/{index}: {warning}")
        if normalized_card is not None:
            signature = card_signature(normalized_card)
            fact_signature = normalize_whitespace(normalized_card["fact_statement"]).lower()
            if signature in seen_signatures:
                warnings.append(
                    f"{pair_id}/{side_name}/{index}: duplicate relation/answer signature skipped"
                )
                continue
            if fact_signature in seen_fact_statements:
                warnings.append(
                    f"{pair_id}/{side_name}/{index}: duplicate fact_statement skipped"
                )
                continue
            seen_signatures.add(signature)
            seen_fact_statements.add(fact_signature)
            normalized_topic["knowledge_cards"].append(normalized_card)
    return normalized_topic, warnings


def normalize_pair_output(
    source_pair: Dict[str, Any],
    model_output: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    pair_id = source_pair["pair_id"]
    warnings: List[str] = []
    target_type, neighbor_type = split_pair_topic_types(source_pair["topic_type"])

    generated_target = model_output.get("target") or {}
    generated_neighbor = model_output.get("neighbor") or {}
    target_topic, target_warnings = normalize_topic_payload(
        pair_id=pair_id,
        side_name="target",
        source_topic=source_pair["target"],
        generated_topic=generated_target,
        default_topic_type=target_type,
    )
    neighbor_topic, neighbor_warnings = normalize_topic_payload(
        pair_id=pair_id,
        side_name="neighbor",
        source_topic=source_pair["neighbor"],
        generated_topic=generated_neighbor,
        default_topic_type=neighbor_type,
    )
    warnings.extend(target_warnings)
    warnings.extend(neighbor_warnings)

    normalized_pair = {
        "pair_id": pair_id,
        "topic_type": source_pair["topic_type"],
        "target": target_topic,
        "neighbor": neighbor_topic,
    }
    return normalized_pair, warnings


def load_or_generate_pair(
    session: requests.Session,
    args: argparse.Namespace,
    pair: Dict[str, Any],
    cache_dir: Path,
) -> Tuple[Dict[str, Any], List[str]]:
    pair_id = pair["pair_id"]
    raw_path = cache_dir / f"{pair_id}.raw.json"
    normalized_path = cache_dir / f"{pair_id}.normalized.json"

    if normalized_path.exists() and not args.refresh_cache:
        cached_normalized = read_json(normalized_path)
        if cached_normalized.get("prompt_version") == PROMPT_VERSION:
            return ensure_pair_card_ids(copy.deepcopy(cached_normalized["pair"])), cached_normalized.get("warnings", [])

    raw_payload: Optional[Dict[str, Any]] = None
    if raw_path.exists() and not args.refresh_cache:
        cached_raw = read_json(raw_path)
        if cached_raw.get("prompt_version") == PROMPT_VERSION:
            raw_payload = cached_raw

    if raw_payload is None:
        blueprint_prompt = build_blueprint_prompt(
            pair=pair,
            max_cards_per_topic=args.max_cards_per_topic,
            min_multi_instance_cards_per_topic=args.min_multi_instance_cards_per_topic,
        )
        blueprint_response_json = call_chat_completion(
            session=session,
            api_base=args.api_base,
            api_keys=args.api_keys,
            model=args.model,
            system_prompt=BLUEPRINT_SYSTEM_PROMPT,
            user_prompt=blueprint_prompt,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        blueprint_output = parse_model_json_response(blueprint_response_json)

        extraction_prompt = build_extraction_prompt(
            pair=pair,
            blueprint=blueprint_output,
            max_cards_per_topic=args.max_cards_per_topic,
            min_multi_instance_cards_per_topic=args.min_multi_instance_cards_per_topic,
        )
        extraction_response_json = call_chat_completion(
            session=session,
            api_base=args.api_base,
            api_keys=args.api_keys,
            model=args.model,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=extraction_prompt,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        raw_payload = {
            "pair_id": pair_id,
            "prompt_version": PROMPT_VERSION,
            "generated_at": utc_now(),
            "model": args.model,
            "api_base": normalize_api_base(args.api_base),
            "blueprint": blueprint_output,
            "blueprint_response": blueprint_response_json,
            "extraction_response": extraction_response_json,
        }
        write_json_atomic(raw_path, raw_payload)

    model_output = parse_model_json_response(raw_payload["extraction_response"])
    normalized_pair, warnings = normalize_pair_output(pair, model_output)
    normalized_pair = ensure_pair_card_ids(normalized_pair)

    cached_normalized = {
        "prompt_version": PROMPT_VERSION,
        "pair": normalized_pair,
        "warnings": warnings,
        "normalized_at": utc_now(),
    }
    write_json_atomic(normalized_path, cached_normalized)
    return normalized_pair, warnings


def build_output_document(
    source_file: str,
    model: str,
    api_base: str,
    max_cards_per_topic: int,
    pairs: List[Dict[str, Any]],
    warnings: List[str],
) -> Dict[str, Any]:
    return {
        "step": "Step 3 knowledge card extraction",
        "prompt_version": PROMPT_VERSION,
        "generated_at": utc_now(),
        "source_file": source_file,
        "model": model,
        "api_base": normalize_api_base(api_base),
        "max_cards_per_topic": max_cards_per_topic,
        "warning_count": len(warnings),
        "warnings": warnings,
        "topic_pairs": pairs,
    }


def main() -> None:
    args = parse_args()
    resolve_runtime_settings(args)
    ensure_api_args(args)

    input_path = Path(args.input)
    output_path = Path(args.output)
    cache_dir = Path(args.cache_dir)

    source_data = read_json(input_path)
    source_pairs = filter_pairs(source_data.get("topic_pairs", []), args)
    if not source_pairs:
        raise SystemExit("No topic pairs selected.")

    existing_pairs = {} if args.overwrite else load_existing_output(output_path)
    final_pairs_by_id: Dict[str, Dict[str, Any]] = dict(existing_pairs)
    all_warnings: List[str] = []

    session = requests.Session()
    start_time = time.time()

    for index, pair in enumerate(source_pairs, start=1):
        pair_id = pair["pair_id"]
        log(f"[{index}/{len(source_pairs)}] Processing {pair_id}")
        normalized_pair, warnings = load_or_generate_pair(
            session=session,
            args=args,
            pair=pair,
            cache_dir=cache_dir,
        )
        if args.merge_output and pair_id in final_pairs_by_id:
            normalized_pair = merge_topic_cards(final_pairs_by_id[pair_id], normalized_pair)
        final_pairs_by_id[pair_id] = normalized_pair
        all_warnings.extend(warnings)

        ordered_pairs = [
            final_pairs_by_id[item["pair_id"]]
            for item in source_data.get("topic_pairs", [])
            if item["pair_id"] in final_pairs_by_id
        ]
        document = build_output_document(
            source_file=str(input_path),
            model=args.model,
            api_base=args.api_base,
            max_cards_per_topic=args.max_cards_per_topic,
            pairs=ordered_pairs,
            warnings=all_warnings,
        )
        write_json_atomic(output_path, document)
        log(
            f"  target cards={len(normalized_pair['target']['knowledge_cards'])}, "
            f"neighbor cards={len(normalized_pair['neighbor']['knowledge_cards'])}, "
            f"warnings={len(warnings)}"
        )

    elapsed = time.time() - start_time
    log(f"Finished {len(source_pairs)} pair(s) in {elapsed:.1f}s. Output: {output_path}")


if __name__ == "__main__":
    main()
