from __future__ import annotations

from archive_memory.config import ArchiveConfig
from archive_memory.frontmatter import parse_frontmatter
from archive_memory.models import Classification, SourceItem
from archive_memory.utils import read_text_lossy


def classify(item: SourceItem, config: ArchiveConfig) -> Classification:
    text = read_text_lossy(item.source_path)
    frontmatter, body = parse_frontmatter(text)
    title = _title_from(item, frontmatter, body)
    project_hint = _project_hint(item, frontmatter)

    if item.source_system == "claude_code":
        if item.source_kind == "skill":
            return Classification("agent", config.claude_agent_id, "agent_skill", project_hint, title)
        if item.source_kind.startswith("claude_md"):
            return Classification("user", config.user_id, "reference", project_hint, title)
        if item.source_kind == "auto_memory_index":
            return Classification("agent", config.claude_agent_id, "reference", project_hint, title)
        if item.source_kind in {"auto_memory_topic", "rule"}:
            return Classification("agent", config.claude_agent_id, "agent_case", project_hint, title)
        return Classification("agent", config.claude_agent_id, "reference", project_hint, title)

    if item.source_system == "codex":
        if item.source_kind == "skill":
            return Classification("agent", config.codex_agent_id, "agent_skill", project_hint, title)
        if item.source_kind == "rollout_summary":
            return Classification("agent", config.codex_agent_id, "agent_case", project_hint, title)
        if item.source_kind in {"summary", "raw_memory", "ad_hoc_note"}:
            return Classification("user", config.user_id, "reference", project_hint, title)
        if item.source_kind == "memory_index":
            return Classification("agent", config.codex_agent_id, "reference", project_hint, title)
        return Classification("agent", config.codex_agent_id, "reference", project_hint, title)

    return Classification("agent", "unknown", "reference", project_hint, title)


def _title_from(item: SourceItem, frontmatter: dict[str, object], body: str) -> str:
    for key in ("title", "name", "description"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return stripped[:100]
    return item.source_path.stem.replace("-", " ").replace("_", " ").strip() or item.source_path.name


def _project_hint(item: SourceItem, frontmatter: dict[str, object]) -> str:
    desc = frontmatter.get("description")
    if isinstance(desc, str) and "/Users/" in desc:
        return desc
    parts = item.source_path.parts
    if "projects" in parts:
        idx = parts.index("projects")
        if idx + 1 < len(parts):
            return parts[idx + 1].replace("-", "/").replace("//", "/")
    return ""
