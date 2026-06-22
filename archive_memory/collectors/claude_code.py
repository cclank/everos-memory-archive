from __future__ import annotations

from pathlib import Path

from archive_memory.collectors.common import build_item
from archive_memory.config import ArchiveConfig
from archive_memory.models import SourceItem


def collect(config: ArchiveConfig) -> list[SourceItem]:
    items: list[SourceItem] = []
    root = config.claude_root
    if not root.exists():
        return items

    global_claude = root / "CLAUDE.md"
    item = build_item("claude_code", "claude_md_user", global_claude, root)
    if item:
        items.append(item)

    for path in sorted((root / "projects").glob("*/memory/*.md")):
        kind = "auto_memory_index" if path.name == "MEMORY.md" else "auto_memory_topic"
        item = build_item("claude_code", kind, path, root)
        if item:
            items.append(item)

    for path in sorted((root / "skills").glob("**/SKILL.md")):
        item = build_item("claude_code", "skill", path, root)
        if item:
            items.append(item)

    for repo_root in config.repo_roots:
        if repo_root.exists():
            items.extend(_collect_repo_files(repo_root))

    return items


def _collect_repo_files(repo_root: Path) -> list[SourceItem]:
    items: list[SourceItem] = []
    for path in sorted(repo_root.glob("*/CLAUDE.md")):
        item = build_item("claude_code", "claude_md_project", path, repo_root)
        if item:
            items.append(item)
    for path in sorted(repo_root.glob("*/.claude/CLAUDE.md")):
        item = build_item("claude_code", "claude_md_project", path, repo_root)
        if item:
            items.append(item)
    for path in sorted(repo_root.glob("*/CLAUDE.local.md")):
        item = build_item("claude_code", "claude_md_local", path, repo_root)
        if item:
            items.append(item)
    for path in sorted(repo_root.glob("*/.claude/skills/**/SKILL.md")):
        item = build_item("claude_code", "skill", path, repo_root)
        if item:
            items.append(item)
    for path in sorted(repo_root.glob("*/.claude/rules/*.md")):
        item = build_item("claude_code", "rule", path, repo_root)
        if item:
            items.append(item)
    return items
