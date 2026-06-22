from __future__ import annotations

from archive_memory.collectors import claude_code, codex
from archive_memory.config import ArchiveConfig
from archive_memory.models import SourceItem


def parse_sources(value: str) -> set[str]:
    normalized = {part.strip().lower() for part in value.split(",") if part.strip()}
    if not normalized or "all" in normalized:
        return {"claude", "codex"}
    aliases = {"claude_code": "claude", "claude-code": "claude"}
    return {aliases.get(item, item) for item in normalized}


def scan(config: ArchiveConfig, source_filter: str = "all") -> list[SourceItem]:
    sources = parse_sources(source_filter)
    items: list[SourceItem] = []
    if "claude" in sources:
        items.extend(claude_code.collect(config))
    if "codex" in sources:
        items.extend(codex.collect(config))
    return sorted(items, key=lambda i: (i.source_system, i.source_kind, i.relative_path))
