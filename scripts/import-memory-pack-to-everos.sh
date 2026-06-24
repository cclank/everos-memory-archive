#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

cd "${REPO_ROOT}"

echo "Importing compiled Memory Pack into EverOS..."
exec "${PYTHON_BIN}" -m archive_memory everos-import "$@"
