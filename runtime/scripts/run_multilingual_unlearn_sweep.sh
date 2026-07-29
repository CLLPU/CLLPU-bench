#!/usr/bin/env bash
set -euo pipefail

# General multilingual unlearning sweep runner.
#
# Default sweep:
#   method=NPO, source_language=en
#   learning_rate in {1e-5,3e-5,5e-5}
#   alpha/lambda in {1.0}
#   beta in {0.1,0.5}
#   gamma in {1.0}
#
# Default SimNPO sweep when --methods simnpo:
#   learning_rate in {1e-5,3e-5,5e-5}
#   beta in {3.5,4.5}
#   delta in {1}
#   gamma in {0.125,0.25}
#
# BalDRO-DV variants:
#   --methods drnpo,drsimnpo
#   DrNPO beta_dv_forget in {2,5}
#   DrSimNPO sigma_forget in {2,5}
#   Retain-side DV strength remains 1.0 and retain-side DRO is disabled by default.
#
# Typical usage:
#   bash runtime/scripts/run_multilingual_unlearn_sweep.sh --dry-run
#   bash runtime/scripts/run_multilingual_unlearn_sweep.sh

GPU_ID="${GPU_ID:-3}"
SOURCE_LANGUAGE="${SOURCE_LANGUAGE:-en}"
METHODS_CSV="${METHODS_CSV:-npo}"
LEARNING_RATES_CSV="${LEARNING_RATES_CSV:-1e-5,3e-5,5e-5}"
BETAS_CSV="${BETAS_CSV:-0.1,0.5}"
ALPHAS_CSV="${ALPHAS_CSV:-1.0}"
GAMMAS_CSV="${GAMMAS_CSV:-1.0}"
SIMNPO_BETAS_CSV="${SIMNPO_BETAS_CSV:-3.5,4.5}"
SIMNPO_GAMMAS_CSV="${SIMNPO_GAMMAS_CSV:-0.125,0.25}"
SIMNPO_DELTAS_CSV="${SIMNPO_DELTAS_CSV:-1}"
DRNPO_DV_FORGETS_CSV="${DRNPO_DV_FORGETS_CSV:-2,5}"
DRNPO_DV_RETAINS_CSV="${DRNPO_DV_RETAINS_CSV:-1.0}"
DRSIMNPO_SIGMA_FORGETS_CSV="${DRSIMNPO_SIGMA_FORGETS_CSV:-2,5}"
DRSIMNPO_SIGMA_RETAINS_CSV="${DRSIMNPO_SIGMA_RETAINS_CSV:-1.0}"
BALDRO_FORGET_DRO="${BALDRO_FORGET_DRO:-true}"
BALDRO_RETAIN_DRO="${BALDRO_RETAIN_DRO:-false}"
BALDRO_LOG_ORI_LOSS="${BALDRO_LOG_ORI_LOSS:-true}"
NUM_EPOCHS="${NUM_EPOCHS:-10}"
PER_DEVICE_BATCH="${PER_DEVICE_BATCH:-8}"
GRAD_ACCUM="${GRAD_ACCUM:-4}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.01}"
WARMUP_EPOCHS="${WARMUP_EPOCHS:-1.0}"
OPTIM="${OPTIM:-paged_adamw_32bit}"
MODEL_CONFIG="${MODEL_CONFIG:-Llama-3.1-8B-Instruct}"
FINETUNED_MODEL="${FINETUNED_MODEL:-${CROSS_LINGUAL_TARGET_MODEL:-}}"
EXPERIMENT_CONFIG="${EXPERIMENT_CONFIG:-unlearn/multilingual/default}"
RUN_NAME_PREFIX="${RUN_NAME_PREFIX:-multilingual}"
OUTPUT_ROOT="${OUTPUT_ROOT:-outputs/unlearn}"
WANDB_PROJECT="${WANDB_PROJECT:-multilingual-unlearning-unlearn}"
SAVE_FINAL_MODEL="${SAVE_FINAL_MODEL:-false}"
SAVE_ONLY_MODEL="${SAVE_ONLY_MODEL:-true}"
SAVE_TOTAL_LIMIT="${SAVE_TOTAL_LIMIT:-null}"
TRAIN_EVAL="${TRAIN_EVAL:-true}"
POST_TRAIN_EVAL="${POST_TRAIN_EVAL:-false}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-32}"
EVAL_METRICS_CSV="${EVAL_METRICS_CSV:-a_exact,a_rouge}"
WANDB_ENTITY="${WANDB_ENTITY:-}"
REPORT_TO="${REPORT_TO:-none}"
CONDA_ENV="${CONDA_ENV:-}"
ALLOW_EXISTING=0
SKIP_EXISTING=0
DRY_RUN=0
PRECHECK_ONLY=0
EXTRA_OVERRIDES=()
declare -A SEEN_OUTPUT_DIRS=()

usage() {
  cat <<'USAGE'
Usage:
  bash runtime/scripts/run_multilingual_unlearn_sweep.sh [options]

Common options:
  --dry-run                         Print commands without running them.
  --gpu ID                          CUDA_VISIBLE_DEVICES value. Default: 3.
  --source-language LANG            Source language to unlearn. Default: en.
  --methods CSV                     Methods: ga,gd,npo,simnpo,drnpo,drsimnpo. Default: npo.
  --learning-rates CSV              LR sweep. Default: 1e-5,3e-5,5e-5.
  --betas CSV                       Beta sweep for NPO/DrNPO. Default: 0.1,0.5.
  --alphas CSV                      Retain-loss weight/lambda sweep. Default: 1.0.
  --gammas CSV                      Forget/NPO loss weight sweep for GD/NPO. Default: 1.0.
  --simnpo-betas CSV                SimNPO beta sweep. Default: 3.5,4.5.
  --simnpo-gammas CSV               SimNPO gamma sweep. Default: 0.125,0.25.
  --simnpo-deltas CSV               SimNPO/DrSimNPO delta sweep. Default: 1.
  --drnpo-dv-forgets CSV            BalDRO-DV forget beta sweep for DrNPO. Default: 2,5.
  --drnpo-dv-retains CSV            BalDRO-DV retain beta sweep for DrNPO. Default: 1.0.
  --drsimnpo-sigma-forgets CSV      BalDRO-DV forget sigma sweep for DrSimNPO. Default: 2,5.
  --drsimnpo-sigma-retains CSV      BalDRO-DV retain sigma sweep for DrSimNPO. Default: 1.0.
  --baldro-forget-dro true|false    Enable forget-side DV aggregation. Default: true.
  --baldro-retain-dro true|false    Enable retain-side DV aggregation. Default: false.
  --baldro-log-ori-loss true|false  Log pre-DV mean loss. Default: true.
  --epochs N                        Number of epochs. Default: 10.
  --batch-size N                    per_device_train_batch_size. Default: 8.
  --grad-accum N                    gradient_accumulation_steps. Default: 4.
  --weight-decay X                  Weight decay. Default: 0.01.
  --warmup-epochs X                 Linear warmup epochs. Default: 1.0.
  --optim NAME                      Optimizer. Default: paged_adamw_32bit.
  --finetuned-model ID_OR_PATH      Required target model used as the unlearning start.
  --model-config NAME               Hydra model config name. Default: Llama-3.1-8B-Instruct.
  --experiment-config NAME          Hydra experiment config. Default: unlearn/multilingual/default.
  --run-name-prefix PREFIX          Run-name prefix. Default: multilingual.
  --output-root DIR                 Root directory for run outputs. Default: outputs/unlearn.
  --wandb-project NAME              W&B project. Default: multilingual-unlearning-unlearn.
  --save-final-model true|false     Save final model after training. Default: false.
  --save-only-model true|false      Save model-only epoch checkpoints. Default: true.
  --save-total-limit VALUE          HF save_total_limit. Default: null.
  --train-eval true|false           Run source-language Exact/ROUGE screening. Default: true.
  --post-train-eval true|false      Run one extra evaluation after training finishes. Default: false.
  --eval-batch-size N               Source-language screening batch size. Default: 32.
  --eval-metrics CSV                Training-time evaluation metrics. Default: a_exact,a_rouge.
  --wandb-entity NAME               Optional W&B entity for eval upload.
  --report-to NAME                  Trainer integration (for example wandb). Default: none.
  --conda-env NAME                  Optional conda env. Empty uses the current Python.
  --allow-existing                  Allow writing into an existing output directory.
  --skip-existing                   Skip only a completed run with an identical command fingerprint.
  --override KEY=VALUE              Extra Hydra override. May be repeated.
  -h, --help                        Show this help.

Examples:
  bash runtime/scripts/run_multilingual_unlearn_sweep.sh --dry-run
  bash runtime/scripts/run_multilingual_unlearn_sweep.sh --finetuned-model org/target-model --dry-run
  bash runtime/scripts/run_multilingual_unlearn_sweep.sh --learning-rates 1e-5,2e-5 --betas 0.1,0.5
USAGE
}

require_value() {
  local opt="$1"
  local value="${2:-}"
  if [[ -z "${value}" || "${value}" == --* ]]; then
    echo "Missing value for ${opt}" >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --gpu)
      require_value "$1" "${2:-}"
      GPU_ID="$2"
      shift 2
      ;;
    --source-language)
      require_value "$1" "${2:-}"
      SOURCE_LANGUAGE="$2"
      shift 2
      ;;
    --methods)
      require_value "$1" "${2:-}"
      METHODS_CSV="$2"
      shift 2
      ;;
    --learning-rates)
      require_value "$1" "${2:-}"
      LEARNING_RATES_CSV="$2"
      shift 2
      ;;
    --betas)
      require_value "$1" "${2:-}"
      BETAS_CSV="$2"
      shift 2
      ;;
    --simnpo-betas)
      require_value "$1" "${2:-}"
      SIMNPO_BETAS_CSV="$2"
      shift 2
      ;;
    --alphas)
      require_value "$1" "${2:-}"
      ALPHAS_CSV="$2"
      shift 2
      ;;
    --gammas)
      require_value "$1" "${2:-}"
      GAMMAS_CSV="$2"
      shift 2
      ;;
    --simnpo-gammas)
      require_value "$1" "${2:-}"
      SIMNPO_GAMMAS_CSV="$2"
      shift 2
      ;;
    --simnpo-deltas)
      require_value "$1" "${2:-}"
      SIMNPO_DELTAS_CSV="$2"
      shift 2
      ;;
    --drnpo-dv-forgets)
      require_value "$1" "${2:-}"
      DRNPO_DV_FORGETS_CSV="$2"
      shift 2
      ;;
    --drnpo-dv-retains)
      require_value "$1" "${2:-}"
      DRNPO_DV_RETAINS_CSV="$2"
      shift 2
      ;;
    --drsimnpo-sigma-forgets)
      require_value "$1" "${2:-}"
      DRSIMNPO_SIGMA_FORGETS_CSV="$2"
      shift 2
      ;;
    --drsimnpo-sigma-retains)
      require_value "$1" "${2:-}"
      DRSIMNPO_SIGMA_RETAINS_CSV="$2"
      shift 2
      ;;
    --baldro-forget-dro)
      require_value "$1" "${2:-}"
      BALDRO_FORGET_DRO="$2"
      shift 2
      ;;
    --baldro-retain-dro)
      require_value "$1" "${2:-}"
      BALDRO_RETAIN_DRO="$2"
      shift 2
      ;;
    --baldro-log-ori-loss)
      require_value "$1" "${2:-}"
      BALDRO_LOG_ORI_LOSS="$2"
      shift 2
      ;;
    --epochs)
      require_value "$1" "${2:-}"
      NUM_EPOCHS="$2"
      shift 2
      ;;
    --batch-size)
      require_value "$1" "${2:-}"
      PER_DEVICE_BATCH="$2"
      shift 2
      ;;
    --grad-accum)
      require_value "$1" "${2:-}"
      GRAD_ACCUM="$2"
      shift 2
      ;;
    --weight-decay)
      require_value "$1" "${2:-}"
      WEIGHT_DECAY="$2"
      shift 2
      ;;
    --warmup-epochs)
      require_value "$1" "${2:-}"
      WARMUP_EPOCHS="$2"
      shift 2
      ;;
    --optim)
      require_value "$1" "${2:-}"
      OPTIM="$2"
      shift 2
      ;;
    --finetuned-model)
      require_value "$1" "${2:-}"
      FINETUNED_MODEL="$2"
      shift 2
      ;;
    --model-config)
      require_value "$1" "${2:-}"
      MODEL_CONFIG="$2"
      shift 2
      ;;
    --experiment-config)
      require_value "$1" "${2:-}"
      EXPERIMENT_CONFIG="$2"
      shift 2
      ;;
    --run-name-prefix)
      require_value "$1" "${2:-}"
      RUN_NAME_PREFIX="$2"
      shift 2
      ;;
    --output-root)
      require_value "$1" "${2:-}"
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --wandb-project)
      require_value "$1" "${2:-}"
      WANDB_PROJECT="$2"
      shift 2
      ;;
    --wandb-entity)
      require_value "$1" "${2:-}"
      WANDB_ENTITY="$2"
      shift 2
      ;;
    --report-to)
      require_value "$1" "${2:-}"
      REPORT_TO="$2"
      shift 2
      ;;
    --save-final-model)
      require_value "$1" "${2:-}"
      SAVE_FINAL_MODEL="$2"
      shift 2
      ;;
    --save-only-model)
      require_value "$1" "${2:-}"
      SAVE_ONLY_MODEL="$2"
      shift 2
      ;;
    --save-total-limit)
      require_value "$1" "${2:-}"
      SAVE_TOTAL_LIMIT="$2"
      shift 2
      ;;
    --train-eval)
      require_value "$1" "${2:-}"
      TRAIN_EVAL="$2"
      shift 2
      ;;
    --post-train-eval)
      require_value "$1" "${2:-}"
      POST_TRAIN_EVAL="$2"
      shift 2
      ;;
    --eval-batch-size)
      require_value "$1" "${2:-}"
      EVAL_BATCH_SIZE="$2"
      shift 2
      ;;
    --eval-metrics)
      require_value "$1" "${2:-}"
      EVAL_METRICS_CSV="$2"
      shift 2
      ;;
    --conda-env)
      require_value "$1" "${2:-}"
      CONDA_ENV="$2"
      shift 2
      ;;
    --allow-existing)
      ALLOW_EXISTING=1
      shift
      ;;
    --skip-existing)
      SKIP_EXISTING=1
      shift
      ;;
    --override)
      require_value "$1" "${2:-}"
      EXTRA_OVERRIDES+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

csv_to_array() {
  local csv="$1"
  local -n out="$2"
  local item
  local trimmed
  out=()
  IFS=',' read -r -a raw_items <<< "${csv}"
  for item in "${raw_items[@]}"; do
    trimmed="$(echo "${item}" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    if [[ -n "${trimmed}" ]]; then
      out+=("${trimmed}")
    fi
  done
  if [[ "${#out[@]}" -eq 0 ]]; then
    echo "CSV option resolved to an empty list: ${csv}" >&2
    exit 2
  fi
}

csv_to_array "${METHODS_CSV}" METHODS
csv_to_array "${LEARNING_RATES_CSV}" LEARNING_RATES
csv_to_array "${BETAS_CSV}" BETAS
csv_to_array "${ALPHAS_CSV}" ALPHAS
csv_to_array "${GAMMAS_CSV}" GAMMAS
csv_to_array "${SIMNPO_BETAS_CSV}" SIMNPO_BETAS
csv_to_array "${SIMNPO_GAMMAS_CSV}" SIMNPO_GAMMAS
csv_to_array "${SIMNPO_DELTAS_CSV}" SIMNPO_DELTAS
csv_to_array "${DRNPO_DV_FORGETS_CSV}" DRNPO_DV_FORGETS
csv_to_array "${DRNPO_DV_RETAINS_CSV}" DRNPO_DV_RETAINS
csv_to_array "${DRSIMNPO_SIGMA_FORGETS_CSV}" DRSIMNPO_SIGMA_FORGETS
csv_to_array "${DRSIMNPO_SIGMA_RETAINS_CSV}" DRSIMNPO_SIGMA_RETAINS

trainer_name() {
  case "$1" in
    ga|grad_ascent|GradAscent) echo "GradAscent" ;;
    gd|grad_diff|GradDiff) echo "GradDiff" ;;
    npo|NPO) echo "NPO" ;;
    simnpo|SimNPO) echo "SimNPO" ;;
    drnpo|DrNPO) echo "DrNPO" ;;
    drsimnpo|DrSimNPO) echo "DrSimNPO" ;;
    *)
      echo "Unsupported method: $1" >&2
      exit 2
      ;;
  esac
}

method_tag() {
  case "$1" in
    GradAscent) echo "ga" ;;
    GradDiff) echo "gd" ;;
    NPO) echo "npo" ;;
    SimNPO) echo "simnpo" ;;
    DrNPO) echo "drnpo" ;;
    DrSimNPO) echo "drsimnpo" ;;
  esac
}

sanitize() {
  echo "$1" | sed 's/[[:space:]]/_/g; s/\//_/g; s/:/_/g'
}

sanitize_numeric() {
  echo "$1" | sed 's/[[:space:]]/_/g; s/\./p/g; s/-/m/g; s/+//g; s/\//_/g; s/:/_/g'
}

validate_bool() {
  local name="$1"
  local value="$2"
  case "${value}" in
    true|false) ;;
    *)
      echo "${name} must be true or false, got: ${value}" >&2
      exit 2
      ;;
  esac
}

gamma_values_for() {
  case "$1" in
    SimNPO|DrSimNPO) printf '%s\n' "${SIMNPO_GAMMAS[@]}" ;;
    GradDiff|NPO|DrNPO) printf '%s\n' "${GAMMAS[@]}" ;;
    GradAscent) printf '%s\n' "none" ;;
  esac
}

beta_values_for() {
  case "$1" in
    NPO|DrNPO) printf '%s\n' "${BETAS[@]}" ;;
    SimNPO|DrSimNPO) printf '%s\n' "${SIMNPO_BETAS[@]}" ;;
    GradAscent|GradDiff) printf '%s\n' "none" ;;
  esac
}

alpha_values_for() {
  case "$1" in
    GradAscent) printf '%s\n' "none" ;;
    GradDiff|NPO|SimNPO|DrNPO|DrSimNPO) printf '%s\n' "${ALPHAS[@]}" ;;
  esac
}

delta_values_for() {
  case "$1" in
    SimNPO|DrSimNPO) printf '%s\n' "${SIMNPO_DELTAS[@]}" ;;
    GradAscent|GradDiff|NPO|DrNPO) printf '%s\n' "none" ;;
  esac
}

dv_forget_values_for() {
  case "$1" in
    DrNPO) printf '%s\n' "${DRNPO_DV_FORGETS[@]}" ;;
    DrSimNPO) printf '%s\n' "${DRSIMNPO_SIGMA_FORGETS[@]}" ;;
    *) printf '%s\n' "none" ;;
  esac
}

dv_retain_values_for() {
  case "$1" in
    DrNPO) printf '%s\n' "${DRNPO_DV_RETAINS[@]}" ;;
    DrSimNPO) printf '%s\n' "${DRSIMNPO_SIGMA_RETAINS[@]}" ;;
    *) printf '%s\n' "none" ;;
  esac
}

run_command() {
  local trainer="$1"
  local lr="$2"
  local alpha="$3"
  local gamma="$4"
  local beta="$5"
  local delta="$6"
  local dv_forget="$7"
  local dv_retain="$8"
  local tag
  local run_name
  local output_dir
  local eval_strategy
  local -a python_cmd=(python -u)
  local -a cmd
  if [[ -n "${CONDA_ENV}" ]]; then
    python_cmd=(conda run --no-capture-output -n "${CONDA_ENV}" python -u)
  fi
  tag="$(method_tag "${trainer}")"
  eval_strategy="epoch"
  if [[ "${TRAIN_EVAL}" != "true" ]]; then
    eval_strategy="no"
  fi

  run_name="$(sanitize "${RUN_NAME_PREFIX}")_$(sanitize "${MODEL_CONFIG}")_${tag}_$(sanitize "${SOURCE_LANGUAGE}")_lr$(sanitize_numeric "${lr}")"
  if [[ "${trainer}" == "NPO" || "${trainer}" == "SimNPO" || "${trainer}" == "DrNPO" || "${trainer}" == "DrSimNPO" ]]; then
    run_name="${run_name}_beta$(sanitize_numeric "${beta}")"
  fi
  if [[ "${trainer}" == "SimNPO" || "${trainer}" == "DrSimNPO" ]]; then
    run_name="${run_name}_delta$(sanitize_numeric "${delta}")"
  fi
  if [[ "${trainer}" == "DrNPO" ]]; then
    run_name="${run_name}_dvf$(sanitize_numeric "${dv_forget}")"
    if [[ "${BALDRO_RETAIN_DRO}" == "true" ]]; then
      run_name="${run_name}_dvr$(sanitize_numeric "${dv_retain}")"
    fi
  fi
  if [[ "${trainer}" == "DrSimNPO" ]]; then
    run_name="${run_name}_sf$(sanitize_numeric "${dv_forget}")"
    if [[ "${BALDRO_RETAIN_DRO}" == "true" ]]; then
      run_name="${run_name}_sr$(sanitize_numeric "${dv_retain}")"
    fi
  fi
  if [[ "${trainer}" != "GradAscent" ]]; then
    run_name="${run_name}_alpha$(sanitize_numeric "${alpha}")_gamma$(sanitize_numeric "${gamma}")"
  fi
  run_name="${run_name}_b${PER_DEVICE_BATCH}g${GRAD_ACCUM}_${NUM_EPOCHS}epoch"
  output_dir="${OUTPUT_ROOT%/}/${run_name}"

  if [[ -n "${SEEN_OUTPUT_DIRS[${output_dir}]:-}" ]]; then
    echo "Duplicate output directory in this sweep: ${output_dir}" >&2
    echo "Check duplicated grid values or run-name dimensions." >&2
    exit 1
  fi
  SEEN_OUTPUT_DIRS["${output_dir}"]=1

  if [[ "${DRY_RUN}" -eq 0 && -e "${output_dir}" && "${ALLOW_EXISTING}" -eq 0 && "${SKIP_EXISTING}" -eq 0 ]]; then
    echo "Output directory already exists: ${output_dir}" >&2
    echo "Use --skip-existing to skip it, --allow-existing to continue anyway, or choose --output-root." >&2
    exit 1
  fi

  if [[ "${PRECHECK_ONLY}" -eq 1 ]]; then
    return
  fi

  cmd=(
    env
    "WANDB_PROJECT=${WANDB_PROJECT}"
    "WANDB_NAME=${run_name}"
    "CUDA_VISIBLE_DEVICES=${GPU_ID}"
    "${python_cmd[@]}" -m cllpu.train
    --config-name=unlearn.yaml
    "experiment=${EXPERIMENT_CONFIG}"
    "trainer=${trainer}"
    "task_name=${run_name}"
    "paths.output_dir=${output_dir}"
    "model=${MODEL_CONFIG}"
    "target_model=${FINETUNED_MODEL}"
    "multilingual_source_language=${SOURCE_LANGUAGE}"
    "trainer.args.per_device_train_batch_size=${PER_DEVICE_BATCH}"
    "trainer.args.gradient_accumulation_steps=${GRAD_ACCUM}"
    "trainer.args.learning_rate=${lr}"
    "trainer.args.optim=${OPTIM}"
    "trainer.args.weight_decay=${WEIGHT_DECAY}"
    "trainer.args.warmup_epochs=${WARMUP_EPOCHS}"
    "trainer.args.num_train_epochs=${NUM_EPOCHS}"
    "trainer.args.do_eval=${TRAIN_EVAL}"
    "trainer.args.eval_strategy=${eval_strategy}"
    "trainer.args.eval_on_start=false"
    "trainer.args.save_strategy=epoch"
    "trainer.args.save_only_model=${SAVE_ONLY_MODEL}"
    "trainer.args.save_total_limit=${SAVE_TOTAL_LIMIT}"
    "eval.multilingual.batch_size=${EVAL_BATCH_SIZE}"
    "eval.multilingual.metrics.accessibility.metric_names=[${EVAL_METRICS_CSV}]"
    "save_final_model=${SAVE_FINAL_MODEL}"
    "post_train_eval=${POST_TRAIN_EVAL}"
    "trainer.args.report_to=${REPORT_TO}"
    "+trainer.args.run_name=${run_name}"
  )
  if [[ -n "${WANDB_ENTITY}" ]]; then
    cmd=(env "WANDB_PROJECT=${WANDB_PROJECT}" "WANDB_ENTITY=${WANDB_ENTITY}" "WANDB_NAME=${run_name}" "CUDA_VISIBLE_DEVICES=${GPU_ID}" "${cmd[@]:4}")
  fi

  case "${trainer}" in
    GradDiff)
      cmd+=("trainer.method_args.alpha=${alpha}")
      cmd+=("trainer.method_args.gamma=${gamma}")
      ;;
    NPO)
      cmd+=("trainer.method_args.alpha=${alpha}")
      cmd+=("trainer.method_args.gamma=${gamma}")
      cmd+=("trainer.method_args.beta=${beta}")
      ;;
    SimNPO)
      cmd+=("trainer.method_args.alpha=${alpha}")
      cmd+=("trainer.method_args.gamma=${gamma}")
      cmd+=("trainer.method_args.beta=${beta}")
      cmd+=("trainer.method_args.delta=${delta}")
      ;;
    DrNPO)
      cmd+=("trainer.method_args.alpha=${alpha}")
      cmd+=("trainer.method_args.gamma=${gamma}")
      cmd+=("trainer.method_args.beta=${beta}")
      cmd+=("trainer.method_args.beta_dv_forget=${dv_forget}")
      cmd+=("trainer.method_args.beta_dv_retain=${dv_retain}")
      cmd+=("trainer.method_args.forget_dro=${BALDRO_FORGET_DRO}")
      cmd+=("trainer.method_args.retain_dro=${BALDRO_RETAIN_DRO}")
      cmd+=("trainer.method_args.log_ori_loss=${BALDRO_LOG_ORI_LOSS}")
      ;;
    DrSimNPO)
      cmd+=("trainer.method_args.alpha=${alpha}")
      cmd+=("trainer.method_args.gamma=${gamma}")
      cmd+=("trainer.method_args.beta=${beta}")
      cmd+=("trainer.method_args.delta=${delta}")
      cmd+=("trainer.method_args.sigma_forget=${dv_forget}")
      cmd+=("trainer.method_args.sigma_retain=${dv_retain}")
      cmd+=("trainer.method_args.forget_dro=${BALDRO_FORGET_DRO}")
      cmd+=("trainer.method_args.retain_dro=${BALDRO_RETAIN_DRO}")
      cmd+=("trainer.method_args.log_ori_loss=${BALDRO_LOG_ORI_LOSS}")
      ;;
  esac

  if [[ "${#EXTRA_OVERRIDES[@]}" -gt 0 ]]; then
    cmd+=("${EXTRA_OVERRIDES[@]}")
  fi

  printf '%q ' "${cmd[@]}"
  printf '\n'

  if [[ "${DRY_RUN}" -eq 0 ]]; then
    local completion_marker="${output_dir}/.crosslingual_run_complete"
    local command_fingerprint
    local data_root_identity
    local config_root_identity
    data_root_identity="$(realpath -m -- "${CROSS_LINGUAL_DATA_DIR:-runtime/data}")"
    config_root_identity="$(realpath -m -- "${CROSS_LINGUAL_CONFIG_DIR:-runtime/configs}")"
    command_fingerprint="$({
      printf '%q ' "${cmd[@]}"
      printf '\ndata_root=%q\nconfig_root=%q\n' "${data_root_identity}" "${config_root_identity}"
    } | sha256sum | awk '{print $1}')"
    if [[ -e "${output_dir}" && "${SKIP_EXISTING}" -eq 1 ]]; then
      if [[ -f "${completion_marker}" ]] && [[ "$(<"${completion_marker}")" == "${command_fingerprint}" ]]; then
        echo "Skipping completed run with matching command: ${output_dir}" >&2
        return
      fi
      echo "Refusing to skip incomplete or protocol-mismatched output: ${output_dir}" >&2
      echo "Choose another --output-root, remove the incomplete run, or use --allow-existing explicitly." >&2
      exit 1
    fi
    "${cmd[@]}"
    mkdir -p "${output_dir}"
    printf '%s\n' "${command_fingerprint}" > "${completion_marker}"
  fi
}

run_sweep() {
  for method in "${METHODS[@]}"; do
    trainer="$(trainer_name "${method}")"
    for lr in "${LEARNING_RATES[@]}"; do
      while IFS= read -r alpha; do
        while IFS= read -r gamma; do
          while IFS= read -r delta; do
            if [[ "${trainer}" == "GradAscent" || "${trainer}" == "GradDiff" ]]; then
              run_command "${trainer}" "${lr}" "${alpha}" "${gamma}" "none" "${delta}" "none" "none"
            else
              while IFS= read -r beta; do
                while IFS= read -r dv_forget; do
                  while IFS= read -r dv_retain; do
                    run_command "${trainer}" "${lr}" "${alpha}" "${gamma}" "${beta}" "${delta}" "${dv_forget}" "${dv_retain}"
                  done < <(dv_retain_values_for "${trainer}")
                done < <(dv_forget_values_for "${trainer}")
              done < <(beta_values_for "${trainer}")
            fi
          done < <(delta_values_for "${trainer}")
        done < <(gamma_values_for "${trainer}")
      done < <(alpha_values_for "${trainer}")
    done
  done
}

reset_seen_output_dirs() {
  unset SEEN_OUTPUT_DIRS
  declare -g -A SEEN_OUTPUT_DIRS=()
}

main() {
  local script_dir
  local repository_root
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  repository_root="$(cd "${script_dir}/../.." && pwd)"
  cd "${repository_root}"
  validate_bool "SAVE_FINAL_MODEL" "${SAVE_FINAL_MODEL}"
  validate_bool "SAVE_ONLY_MODEL" "${SAVE_ONLY_MODEL}"
  validate_bool "TRAIN_EVAL" "${TRAIN_EVAL}"
  validate_bool "POST_TRAIN_EVAL" "${POST_TRAIN_EVAL}"
  validate_bool "BALDRO_FORGET_DRO" "${BALDRO_FORGET_DRO}"
  validate_bool "BALDRO_RETAIN_DRO" "${BALDRO_RETAIN_DRO}"
  validate_bool "BALDRO_LOG_ORI_LOSS" "${BALDRO_LOG_ORI_LOSS}"
  if [[ "${ALLOW_EXISTING}" -eq 1 && "${SKIP_EXISTING}" -eq 1 ]]; then
    echo "--allow-existing and --skip-existing are mutually exclusive." >&2
    exit 2
  fi
  if [[ -z "${FINETUNED_MODEL}" ]]; then
    echo "A target model is required. Pass --finetuned-model ID_OR_PATH or set CROSS_LINGUAL_TARGET_MODEL." >&2
    exit 2
  fi

  PRECHECK_ONLY=1
  run_sweep
  reset_seen_output_dirs

  PRECHECK_ONLY=0
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    mkdir -p "${OUTPUT_ROOT}"
  fi
  run_sweep
}

main "$@"
