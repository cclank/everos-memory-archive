#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_PWD="$(pwd)"

CONFIG_ARGS=()
IMPORT_ARGS=()

resolve_config_path() {
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
      CONFIG_ARGS=(--config "$(resolve_config_path "$2")")
      shift 2
      ;;
    --config=*)
      CONFIG_ARGS=(--config "$(resolve_config_path "${1#--config=}")")
      shift
      ;;
    *)
      IMPORT_ARGS+=("$1")
      shift
      ;;
  esac
done

BACKUP_CMD=("${SCRIPT_DIR}/backup-agent-memories.sh")
IMPORT_CMD=("${SCRIPT_DIR}/import-memory-pack-to-everos.sh")

if [[ "${#CONFIG_ARGS[@]}" -gt 0 ]]; then
  BACKUP_CMD+=("${CONFIG_ARGS[@]}")
  IMPORT_CMD+=("${CONFIG_ARGS[@]}")
fi
if [[ "${#IMPORT_ARGS[@]}" -gt 0 ]]; then
  IMPORT_CMD+=("${IMPORT_ARGS[@]}")
fi

"${BACKUP_CMD[@]}"
"${IMPORT_CMD[@]}"
