# everos-memory-archive

`everos-memory-archive` is a read-only importer for backing up local Codex and Claude Code memories into an EverOS-style archive.

It never writes to:

- `~/.claude`
- `~/.codex`
- `~/.codex/memories`

It only reads those directories and writes archive output under:

```text
~/.everos/agent_memory_archive/
```

## Commands

Run from this repository:

```bash
cd /path/to/everos-memory-archive

# Write a local config file.
python -m archive_memory.cli init-config --path configs/local.toml

# Preview what will be collected.
python -m archive_memory.cli scan --dry-run

# Import changed memories.
python -m archive_memory.cli import --source claude,codex --incremental

# Daily sync: import changes, keep immutable source versions, then verify.
python -m archive_memory.cli sync --source claude,codex

# Compile archived records into a local Memory Pack.
python -m archive_memory.cli compile

# Search archived records.
python -m archive_memory.cli search "EverOS memory"

# Show archive statistics.
python -m archive_memory.cli stats

# Verify archive integrity and safety.
python -m archive_memory.cli verify

# Show latest import report.
python -m archive_memory.cli report --latest

# Show one archived record.
python -m archive_memory.cli show --id <archive_id>
```

After packaging or publishing, the same commands are available as:

```bash
everos-memory-archive scan --dry-run
everos-memory-archive sync --source claude,codex
everos-memory-archive compile
everos-memory-archive verify
```

## Codex Skill

An optional local Codex skill can be installed for this workflow:

```text
~/.codex/skills/archive-agent-memories/SKILL.md
```

Use it in a future Codex thread with:

```text
Use $archive-agent-memories to sync and verify my local Codex and Claude Code memory archive.
```

## Output Layout

```text
~/.everos/agent_memory_archive/
  claude_code/
    sources/
      memory.md
      memory.md.versions/
        <sha256>.md
    records/
      user/<user_id>/
      agents/claude-code/
  codex/
    sources/
      memory_summary.md
      memory_summary.md.versions/
        <sha256>.md
    records/
      user/<user_id>/
      agents/codex/
  unified_index/
    manifest.sqlite
    reports/
  compiled/
    README.md
    memory_map.md
    recent_changes.md
    user_preferences.md
    agent_skills.md
    project_cases.md
    conflicts.md
    bootstrap_context.md
```

`claude_code/` and `codex/` store source-specific redacted snapshots and normalized Markdown cards. With `sync` or `import --keep-versions`, each changed source snapshot is also stored under `*.versions/<sha256>.md`, while the direct file path remains the latest readable copy. `unified_index/manifest.sqlite` stores hashes, versions, paths, and import status for cross-source search and verification.

## Memory Pack Compile

`compile` builds a deterministic local Memory Pack from archived records:

```bash
python -m archive_memory.cli compile
```

It writes:

- `user_preferences.md`: likely user preferences and standing instructions
- `agent_skills.md`: reusable workflows, runbooks, and skills
- `project_cases.md`: project-centered experience and context
- `bootstrap_context.md`: compact context pack for new agents
- `memory_map.md`, `recent_changes.md`, `conflicts.md`: audit and navigation files

V1 is local and rules-based. It does not call an LLM or any remote API.

## Incremental Sync

`sync` is the recommended daily command:

```bash
python -m archive_memory.cli sync --source claude,codex
```

It reports:

- `added`: newly discovered source memory files
- `changed`: same source path with new content hash
- `moved`: same content hash found at a different path
- `versioned`: already-imported content that needs immutable snapshot backfill
- `skipped`: unchanged source files
- `missing`: previously imported source paths that are no longer visible

Manual imports can also keep immutable snapshots:

```bash
python -m archive_memory.cli import --source claude,codex --incremental --keep-versions
```

## Safety

The importer uses explicit allowlists. It does not scan raw Claude/Codex sessions, credentials, cache folders, shell snapshots, file history, or environment dumps.

Secrets are redacted before snapshots and cards are written.

`verify` checks that every archived snapshot and record exists, remains under the archive root, and is not written inside protected Claude/Codex source roots.
