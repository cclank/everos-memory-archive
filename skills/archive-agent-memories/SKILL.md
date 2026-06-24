---
name: archive-agent-memories
description: Use when the user asks to back up, archive, sync, compile, verify, search, inspect, or explain local Codex and Claude Code memories with everos-memory-archive. This skill performs a one-way read-only collection into a local EverOS-style archive with incremental sync, redaction, version snapshots, SQLite indexing, Memory Pack compilation, reports, and safety checks.
---

# Archive Agent Memories

## One-Sentence Trigger

Use this skill when the user says:

```text
Use $archive-agent-memories to back up my Codex and Claude Code memories.
```

## Default Action

Run the one-click backup from the `everos-memory-archive` repository:

```bash
scripts/backup-agent-memories.sh
```

If the current working directory is not the repository root, locate the checkout or ask for the repo path. If the package is already installed, this command is also acceptable:

```bash
everos-memory-archive backup
```

## EverOS Handoff

If the user asks to use EverOS, import into EverOS, or make memories searchable through EverOS, run the EverOS handoff command instead:

```bash
scripts/backup-to-everos.sh --everos-env-file /path/to/everos-local.env
```

Prerequisites:

- EverOS server is already running locally, usually at:

```text
http://127.0.0.1:8000
```

- EverOS is configured with local model endpoints only. Do not use OpenRouter, DeepInfra, OpenAI, Anthropic, or any other remote model provider for private memory imports.
- Pass `--everos-env-file` or set `EVEROS_MEMORY_ARCHIVE_EVEROS_ENV_FILE` so the importer can verify the model endpoints are loopback URLs before sending Memory Pack contents.

The handoff command first runs the local backup, then imports the compiled Memory Pack into EverOS through:

```text
POST /api/v1/memory/add
POST /api/v1/memory/flush
```

Default EverOS scope:

```text
app_id=agent-memory-archive
project_id=codex-claude-code
```

If the server is not running, explain that local backup still succeeded or can be run independently, and ask the user whether to start/configure EverOS.

If the importer refuses because it cannot prove the EverOS API or model endpoints are local, do not bypass the guard. Reconfigure EverOS to local loopback model endpoints first.

## What The Backup Does

The backup command performs:

1. scan allowlisted Codex and Claude Code memory files
2. compare source paths and SHA-256 hashes for incremental sync
3. read source directories without writing back to them
4. redact common secrets before persistence
5. write redacted source snapshots and immutable hash versions
6. write normalized Markdown memory records
7. update the SQLite manifest
8. write the latest sync report
9. compile the local Memory Pack
10. verify archive integrity, redaction, path containment, and symlink safety

## Safety Rules

- Treat `~/.claude`, `~/.codex`, and `~/.codex/memories` as read-only sources.
- Do not import raw session JSONL files.
- Do not write into Claude Code or Codex source directories.
- Do not copy archive outputs into the code repository.
- Treat generated archives as sensitive local data unless the user explicitly reviews and shares them.
- Keep private memory content local. Never send Memory Pack contents to remote LLM, embedding, rerank, or EverOS API endpoints.
- After code changes, run tests and a real backup before reporting success.

## Verification Commands

```bash
python3 -m compileall archive_memory tests
python3 -m unittest discover -s tests -v
scripts/backup-agent-memories.sh
python3 -m archive_memory verify
```

Success requires `Verification: OK`.
