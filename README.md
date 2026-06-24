# everos-memory-archive

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![License MIT](https://img.shields.io/badge/license-MIT-2EA44F)
![Status Alpha](https://img.shields.io/badge/status-alpha-F59E0B)
![Storage Markdown + SQLite](https://img.shields.io/badge/storage-Markdown%20%2B%20SQLite-4B5563)
![Read Only Sources](https://img.shields.io/badge/source%20mode-read--only-0F766E)

One-click local backup for Codex and Claude Code memories.

`everos-memory-archive` collects local Codex and Claude Code memory files into a readable, deduplicated, traceable, EverOS-style archive. It keeps the original tools untouched, stores redacted Markdown snapshots, writes a SQLite manifest for incremental sync, and compiles a local Memory Pack that future agents can read.

## Why This Exists

Agent memory quickly becomes valuable working capital: user preferences, project commands, repo-specific lessons, repeated workflows, writing rules, debugging history, and tool-specific skills.

Codex and Claude Code store useful memory locally, but their complete memory generation, ranking, and injection behavior is controlled by closed-source products. This tool gives you a vendor-neutral local copy that stays readable and portable.

## One-Click Usage

From the repository:

```bash
scripts/backup-agent-memories.sh
```

Equivalent module form:

```bash
python3 -m archive_memory backup
```

After installation:

```bash
everos-memory-archive backup
```

That single command does the full flow:

```text
scan -> incremental sync -> redaction -> hash/version snapshots -> SQLite manifest -> compile Memory Pack -> verify
```

Expected success signal:

```text
One-click memory backup complete.
Verification: OK
Archive root: ~/.everos/agent_memory_archive
```

## Install

For local development:

```bash
git clone <your-fork-or-repo-url>
cd everos-memory-archive
python3 -m pip install -e .
everos-memory-archive backup
```

No runtime dependencies are required beyond Python 3.9+.

## Use With EverOS

The core backup flow is dependency-free, but the repository also includes a real EverOS handoff step.

Start EverOS separately:

```bash
pip install everos
everos init
everos server start
```

Follow EverOS' generated `.env` comments and fill the required LLM / embedding keys before starting the server. EverOS 1.x requires Python 3.12+.

Then run one command from this repo:

```bash
scripts/backup-to-everos.sh
```

That command runs the local backup first, then imports the compiled Memory Pack into the running EverOS server through:

```text
POST /api/v1/memory/add
POST /api/v1/memory/flush
```

Default EverOS scope:

```text
base_url   = http://127.0.0.1:8000
app_id     = agent-memory-archive
project_id = codex-claude-code
user_id    = <local user>
```

You can pass EverOS options through the script:

```bash
scripts/backup-to-everos.sh \
  --base-url http://127.0.0.1:8000 \
  --app-id agent-memory-archive \
  --project-id codex-claude-code \
  --user-id local-user
```

To import an already compiled Memory Pack without re-running backup:

```bash
scripts/import-memory-pack-to-everos.sh
```

After import, query EverOS directly:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/memory/search \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "local-user",
    "app_id": "agent-memory-archive",
    "project_id": "codex-claude-code",
    "query": "What are my Codex and Claude Code working preferences?",
    "top_k": 5
  }'
```

This is the point where EverOS becomes the retrieval backend. The local archive still owns collection, redaction, snapshots, and provenance; EverOS owns memory extraction, Markdown-backed memory storage, indexing, and `/search`.

## Codex Skill

If you use Codex, pair this repo with a local skill and trigger it in one sentence:

```text
Use $archive-agent-memories to back up my Codex and Claude Code memories.
```

The skill should run:

```bash
cd /path/to/everos-memory-archive
scripts/backup-agent-memories.sh
```

The public skill template is included at:

```text
skills/archive-agent-memories/SKILL.md
```

Install it into Codex by copying that folder to:

```text
~/.codex/skills/archive-agent-memories/
```

## What It Collects

Default source roots:

```text
~/.claude
~/.codex/memories
```

The collectors use explicit allowlists. They include readable memory files such as:

| Source | Collected examples |
|---|---|
| Codex | `memory_summary.md`, `MEMORY.md`, `raw_memories.md`, `rollout_summaries/*.md`, `skills/*/SKILL.md`, `extensions/ad_hoc/notes/*.md` |
| Claude Code | `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`, `.claude/skills/**/SKILL.md`, `.claude/rules/*.md`, project memory topics |

It intentionally skips raw sessions, cache folders, shell snapshots, credentials, telemetry, task state, file history, and JSONL conversation logs.

## Output Layout

Default archive root:

```text
~/.everos/agent_memory_archive/
  claude_code/
    sources/
      <redacted latest snapshots>
      <name>.versions/<sha256>.md
    records/
      user/<user_id>/
      agents/claude-code/
  codex/
    sources/
      <redacted latest snapshots>
      <name>.versions/<sha256>.md
    records/
      user/<user_id>/
      agents/codex/
  unified_index/
    manifest.sqlite
    reports/
      latest.json
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

The archive separates source-specific snapshots from normalized Markdown records:

| Layer | Purpose |
|---|---|
| `sources/` | Redacted source snapshots, readable as plain Markdown |
| `*.versions/<sha256>.md` | Immutable version snapshots for changed source files |
| `records/` | Normalized Markdown memory cards grouped by user or agent |
| `manifest.sqlite` | Hashes, source paths, owner/type metadata, import status, and audit state |
| `compiled/` | Deterministic Memory Pack for agent bootstrap and manual review |

## Memory Pack

`backup` runs `compile` by default. You can also run it directly:

```bash
everos-memory-archive compile
```

Generated files:

| File | Use |
|---|---|
| `bootstrap_context.md` | Compact startup context for a new agent |
| `user_preferences.md` | Likely user preferences and standing instructions |
| `agent_skills.md` | Reusable workflows, runbooks, and tool skills |
| `project_cases.md` | Project-centered experience grouped by inferred project |
| `memory_map.md` | Source, owner, type, and project index |
| `recent_changes.md` | Latest imports and latest source updates |
| `conflicts.md` | Local-rule candidates for stale, duplicate, or conflicting memories |

The current compiler is deterministic and local. It does not call an LLM or remote API.

## Commands

```bash
# One-click default.
scripts/backup-agent-memories.sh

# One-click backup plus EverOS import. Requires a running EverOS server.
scripts/backup-to-everos.sh

# Same flow through the installed CLI.
everos-memory-archive backup

# Import compiled Memory Pack into EverOS without re-running backup.
everos-memory-archive everos-import

# Preview source files without writing.
everos-memory-archive scan --dry-run

# Incremental archive sync only.
everos-memory-archive sync --source claude,codex

# Compile the Memory Pack.
everos-memory-archive compile

# Verify archive integrity and secret redaction.
everos-memory-archive verify

# Search archived records with keyword search.
everos-memory-archive search "local code first"

# Show import counts.
everos-memory-archive stats

# Show latest sync report.
everos-memory-archive report --latest
```

## Configuration

Generate a local config:

```bash
everos-memory-archive init-config --path configs/local.toml
```

Example:

```toml
[sources]
claude_code_root = "~/.claude"
codex_memory_root = "~/.codex/memories"
repo_roots = ["~/code"]

[everos]
output_root = "~/.everos/agent_memory_archive"
user_id = "local-user"

[everos.agents]
claude_code = "claude-code"
codex = "codex"
```

Use it with:

```bash
everos-memory-archive --config configs/local.toml backup
```

## Incremental Sync

`backup` and `sync` both use SHA-256 based incremental state:

| State | Meaning |
|---|---|
| `added` | Newly discovered source memory file |
| `changed` | Same source path, new content hash |
| `moved` | Same content hash appears at a different source path |
| `versioned` | Already-imported content needs an immutable snapshot backfill |
| `skipped` | Source path and hash are already archived |
| `missing` | Previously imported source path is no longer visible |
| `failed` | Import or write failed |

## Security Model

Security goals:

- Treat Codex and Claude Code source roots as read-only.
- Keep archive writes under `output_root`.
- Preserve source paths for audit and provenance.
- Redact common secrets before writing snapshots, records, and metadata.
- Reject source symlink escapes.
- Reject archive output symlink writes.
- Validate manifest paths before `search` and `compile` read records.
- Verify that archived records and snapshots stay under the archive root.

Current redaction covers common assignment forms, JSON-style secrets, OpenAI and Anthropic keys, GitHub tokens, AWS access keys, Bearer tokens, and PEM private key blocks. Redaction is a safety layer, not a substitute for reviewing sensitive local data before publishing or sharing an archive.

Run verification any time:

```bash
everos-memory-archive verify
```

## Development

```bash
python3 -m compileall archive_memory tests
python3 -m unittest discover -s tests -v
python3 -m archive_memory backup
python3 -m archive_memory verify
```

The test suite includes regression coverage for:

- common secret formats and metadata redaction
- source symlink escape prevention
- output symlink overwrite prevention
- manifest path trust in `search` and `compile`
- one-click `backup`

## License

MIT. See [LICENSE](LICENSE).
