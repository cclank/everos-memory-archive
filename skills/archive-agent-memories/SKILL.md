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
- After code changes, run tests and a real backup before reporting success.

## Verification Commands

```bash
python3 -m compileall archive_memory tests
python3 -m unittest discover -s tests -v
scripts/backup-agent-memories.sh
python3 -m archive_memory verify
```

Success requires `Verification: OK`.
