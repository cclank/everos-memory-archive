from __future__ import annotations

from pathlib import Path

from archive_memory.frontmatter import dump_frontmatter
from archive_memory.models import Classification, SourceItem
from archive_memory.utils import utc_iso


def render_record(
    *,
    archive_id: str,
    item: SourceItem,
    classification: Classification,
    redacted_text: str,
    snapshot_path: Path,
    output_root: Path,
    imported_at: str,
) -> str:
    snapshot_rel = snapshot_path.resolve().relative_to(output_root.resolve()).as_posix()
    meta = {
        "archive_id": archive_id,
        "source_system": item.source_system,
        "source_kind": item.source_kind,
        "source_path": item.source_path.as_posix(),
        "source_hash": f"sha256:{item.sha256}",
        "source_mtime": utc_iso(item.mtime),
        "source_size": item.size,
        "imported_at": imported_at,
        "owner_type": classification.owner_type,
        "owner_id": classification.owner_id,
        "memory_type": classification.memory_type,
        "project_hint": classification.project_hint,
        "title": classification.title,
        "raw_snapshot": snapshot_rel,
    }
    return (
        dump_frontmatter(meta)
        + "\n"
        + f"# {classification.title}\n\n"
        + "## Source\n\n"
        + f"- System: `{item.source_system}`\n"
        + f"- Kind: `{item.source_kind}`\n"
        + f"- Original path: `{item.source_path}`\n"
        + f"- Snapshot: `{snapshot_rel}`\n"
        + f"- SHA-256: `{item.sha256}`\n\n"
        + "## Archive Notes\n\n"
        + "This record was imported read-only. The original Claude Code or Codex memory file was not modified.\n\n"
        + "## Redacted Source\n\n"
        + redacted_text.rstrip()
        + "\n"
    )
