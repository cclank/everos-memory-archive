#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
ORIGINAL_PWD="$(pwd)"

CONFIG_ARGS=()
PASSTHROUGH_ARGS=()

resolve_user_path() {
  local value="$1"
  case "${value}" in
    "~"|"~/"*) value="${HOME}${value#\~}" ;;
  esac
  if [[ "${value}" = /* ]]; then
    printf '%s\n' "${value}"
  else
    printf '%s/%s\n' "${ORIGINAL_PWD}" "${value}"
  fi
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --config)
      if [[ "$#" -lt 2 ]]; then
        echo "error: --config requires a path" >&2
        exit 2
      fi
      CONFIG_ARGS=(--config "$(resolve_user_path "$2")")
      shift 2
      ;;
    --config=*)
      CONFIG_ARGS=(--config "$(resolve_user_path "${1#--config=}")")
      shift
      ;;
    --everos-env-file|--file)
      if [[ "$#" -lt 2 ]]; then
        echo "error: $1 requires a path" >&2
        exit 2
      fi
      PASSTHROUGH_ARGS+=("$1" "$(resolve_user_path "$2")")
      shift 2
      ;;
    --everos-env-file=*|--file=*)
      PASSTHROUGH_ARGS+=("${1%%=*}=$(resolve_user_path "${1#*=}")")
      shift
      ;;
    *)
      PASSTHROUGH_ARGS+=("$1")
      shift
      ;;
  esac
done

cd "${REPO_ROOT}"

echo "Importing compiled Memory Pack into EverOS..."
CMD=("${PYTHON_BIN}" -m archive_memory)
if [[ "${#CONFIG_ARGS[@]}" -gt 0 ]]; then
  CMD+=("${CONFIG_ARGS[@]}")
fi
CMD+=(everos-import)
if [[ "${#PASSTHROUGH_ARGS[@]}" -gt 0 ]]; then
  CMD+=("${PASSTHROUGH_ARGS[@]}")
fi
exec "${CMD[@]}"
