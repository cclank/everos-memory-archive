#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

cd "${REPO_ROOT}"

echo "Running one-click Codex / Claude Code memory backup..."
exec "${PYTHON_BIN}" -m archive_memory backup "$@"
