#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/backup-agent-memories.sh"
"${SCRIPT_DIR}/import-memory-pack-to-everos.sh" "$@"
