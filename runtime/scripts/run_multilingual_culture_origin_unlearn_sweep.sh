#!/usr/bin/env bash
set -euo pipefail

# Culture-origin grouped unlearning sweep.
#
# A run with --culture-origin zh forgets only zh-origin culture-specific target/core
# QA in Chinese, retains zh-origin neighbor/core QA in Chinese, and screens
# checkpoints on that origin's Chinese target/neighbor core+surface subset.

SOURCE_LANGUAGE="${SOURCE_LANGUAGE:-}"
CULTURE_ORIGIN="${CULTURE_ORIGIN:-}"
PER_DEVICE_BATCH="${PER_DEVICE_BATCH:-4}"
GRAD_ACCUM="${GRAD_ACCUM:-2}"
RUN_NAME_PREFIX="${RUN_NAME_PREFIX:-multilingual_culture_origin}"
EXPERIMENT_CONFIG="${EXPERIMENT_CONFIG:-unlearn/multilingual/culture_origin}"
WANDB_PROJECT="${WANDB_PROJECT:-multilingual-unlearning-culture-origin}"
METHODS_CSV="${METHODS_CSV:-ga,gd,npo,drnpo,simnpo,drsimnpo}"
BETAS_CSV="${BETAS_CSV:-0.1,0.5}"
SIMNPO_BETAS_CSV="${SIMNPO_BETAS_CSV:-3.5,4.5}"
SIMNPO_DELTAS_CSV="${SIMNPO_DELTAS_CSV:-1}"
DRNPO_DV_FORGETS_CSV="${DRNPO_DV_FORGETS_CSV:-2,5}"
DRSIMNPO_SIGMA_FORGETS_CSV="${DRSIMNPO_SIGMA_FORGETS_CSV:-2,5}"
FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-language)
      if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "Missing value for --source-language" >&2
        exit 2
      fi
      SOURCE_LANGUAGE="$2"
      shift 2
      ;;
    --culture-origin)
      if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "Missing value for --culture-origin" >&2
        exit 2
      fi
      CULTURE_ORIGIN="$2"
      shift 2
      ;;
    --source-language=*)
      SOURCE_LANGUAGE="${1#*=}"
      shift
      ;;
    --culture-origin=*)
      CULTURE_ORIGIN="${1#*=}"
      shift
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

CULTURE_ORIGIN="${CULTURE_ORIGIN:-${SOURCE_LANGUAGE:-en}}"
SOURCE_LANGUAGE="${SOURCE_LANGUAGE:-${CULTURE_ORIGIN}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-outputs/unlearn/${CULTURE_ORIGIN}/culture_origin_${CULTURE_ORIGIN}_train_eval_grid}"

if [[ "${SOURCE_LANGUAGE}" != "${CULTURE_ORIGIN}" ]]; then
  echo "culture-origin protocol requires --source-language to match --culture-origin." >&2
  echo "Got source_language=${SOURCE_LANGUAGE}, culture_origin=${CULTURE_ORIGIN}." >&2
  exit 2
fi

case "${CULTURE_ORIGIN}" in
  ar)
    CULTURE_FORGET_EXPECTED_COUNT="${CULTURE_FORGET_EXPECTED_COUNT:-33}"
    CULTURE_RETAIN_EXPECTED_COUNT="${CULTURE_RETAIN_EXPECTED_COUNT:-33}"
    CULTURE_MONITOR_EXPECTED_COUNT="${CULTURE_MONITOR_EXPECTED_COUNT:-264}"
    ;;
  bn)
    CULTURE_FORGET_EXPECTED_COUNT="${CULTURE_FORGET_EXPECTED_COUNT:-27}"
    CULTURE_RETAIN_EXPECTED_COUNT="${CULTURE_RETAIN_EXPECTED_COUNT:-27}"
    CULTURE_MONITOR_EXPECTED_COUNT="${CULTURE_MONITOR_EXPECTED_COUNT:-216}"
    ;;
  de|en|es|fr|ja|sw|th|zh)
    CULTURE_FORGET_EXPECTED_COUNT="${CULTURE_FORGET_EXPECTED_COUNT:-30}"
    CULTURE_RETAIN_EXPECTED_COUNT="${CULTURE_RETAIN_EXPECTED_COUNT:-30}"
    CULTURE_MONITOR_EXPECTED_COUNT="${CULTURE_MONITOR_EXPECTED_COUNT:-240}"
    ;;
  *)
    echo "Unsupported culture origin: ${CULTURE_ORIGIN}" >&2
    exit 2
    ;;
esac

export SOURCE_LANGUAGE
export PER_DEVICE_BATCH
export GRAD_ACCUM
export OUTPUT_ROOT
export RUN_NAME_PREFIX
export EXPERIMENT_CONFIG
export WANDB_PROJECT
export METHODS_CSV
export BETAS_CSV
export SIMNPO_BETAS_CSV
export SIMNPO_DELTAS_CSV
export DRNPO_DV_FORGETS_CSV
export DRSIMNPO_SIGMA_FORGETS_CSV

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec bash "${SCRIPT_DIR}/run_multilingual_unlearn_sweep.sh" \
  --source-language "${SOURCE_LANGUAGE}" \
  --batch-size "${PER_DEVICE_BATCH}" \
  --grad-accum "${GRAD_ACCUM}" \
  --output-root "${OUTPUT_ROOT}" \
  --wandb-project "${WANDB_PROJECT}" \
  --experiment-config "${EXPERIMENT_CONFIG}" \
  --run-name-prefix "${RUN_NAME_PREFIX}" \
  --override "multilingual_culture_origin=${CULTURE_ORIGIN}" \
  --override "multilingual_source_language=${SOURCE_LANGUAGE}" \
  --override "multilingual_culture_forget_expected_count=${CULTURE_FORGET_EXPECTED_COUNT}" \
  --override "multilingual_culture_retain_expected_count=${CULTURE_RETAIN_EXPECTED_COUNT}" \
  --override "multilingual_culture_monitor_expected_count=${CULTURE_MONITOR_EXPECTED_COUNT}" \
  "${FORWARD_ARGS[@]}"
