from __future__ import annotations

from archive_memory.collectors.common import build_item
from archive_memory.config import ArchiveConfig
from archive_memory.models import SourceItem


ROOT_FILES = {
    "memory_summary.md": "summary",
    "MEMORY.md": "memory_index",
    "raw_memories.md": "raw_memory",
}


def collect(config: ArchiveConfig) -> list[SourceItem]:
    items: list[SourceItem] = []
    root = config.codex_memory_root
    if not root.exists():
        return items

    for name, kind in ROOT_FILES.items():
        item = build_item("codex", kind, root / name, root)
        if item:
            items.append(item)

    for path in sorted((root / "rollout_summaries").glob("*.md")):
        item = build_item("codex", "rollout_summary", path, root)
        if item:
            items.append(item)

    for path in sorted((root / "skills").glob("*/SKILL.md")):
        item = build_item("codex", "skill", path, root)
        if item:
            items.append(item)

    for path in sorted((root / "extensions" / "ad_hoc" / "notes").glob("*.md")):
        item = build_item("codex", "ad_hoc_note", path, root)
        if item:
            items.append(item)

    return items
