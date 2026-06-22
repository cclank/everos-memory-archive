from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from archive_memory.config import ArchiveConfig
from archive_memory.manifest import Manifest
from archive_memory.utils import read_text_lossy, utc_iso


@dataclass(frozen=True)
class CompiledItem:
    archive_id: str
    title: str
    source_system: str
    source_kind: str
    owner_id: str
    memory_type: str
    project_hint: str
    imported_at: str
    source_mtime: float
    source_path: Path
    record_path: Path
    snapshot_path: Path
    text: str
    excerpt: str


@dataclass(frozen=True)
class CompileResult:
    output_dir: Path
    files: list[Path]
    item_count: int


PREFERENCE_TERMS = (
    "prefer",
    "preference",
    "用户偏好",
    "偏好",
    "喜欢",
    "要求",
    "不要",
    "避免",
    "avoid",
    "always",
    "never",
    "默认",
    "中文",
    "结构化",
    "直接",
    "本地代码",
    "local code",
    "先看",
    "verify",
    "验证",
)

SKILL_TERMS = (
    "workflow",
    "runbook",
    "procedure",
    "trigger",
    "when to use",
    "skill",
    "sop",
    "流程",
    "步骤",
    "使用",
)

STALE_TERMS = ("stale", "outdated", "deprecated", "过期", "旧", "不准", "可能变化")
STOCK_CONTRAST_PATTERN = re.compile(r"\u4e0d\u662f.{0,80}?\u800c\u662f")
STOCK_YI_DAO_PHRASE = "\u0078\u0078\u0078 \u7684\u4e00\u5200"


def compile_archive(
    config: ArchiveConfig,
    *,
    max_items_per_section: int = 40,
    bootstrap_limit: int = 24,
) -> CompileResult:
    manifest = Manifest(config.manifest_path)
    items = load_compiled_items(config, manifest)
    output_dir = config.output_root / "compiled"
    output_dir.mkdir(parents=True, exist_ok=True)

    files = [
        write_file(output_dir / "README.md", render_readme(config, items)),
        write_file(output_dir / "memory_map.md", render_memory_map(config, items, max_items_per_section)),
        write_file(output_dir / "recent_changes.md", render_recent_changes(config, items, max_items_per_section)),
        write_file(output_dir / "user_preferences.md", render_user_preferences(config, items, max_items_per_section)),
        write_file(output_dir / "agent_skills.md", render_agent_skills(config, items, max_items_per_section)),
        write_file(output_dir / "project_cases.md", render_project_cases(config, items, max_items_per_section)),
        write_file(output_dir / "conflicts.md", render_conflicts(config, items, max_items_per_section)),
        write_file(output_dir / "bootstrap_context.md", render_bootstrap_context(config, items, bootstrap_limit)),
    ]
    return CompileResult(output_dir=output_dir, files=files, item_count=len(items))


def load_compiled_items(config: ArchiveConfig, manifest: Manifest) -> list[CompiledItem]:
    items: list[CompiledItem] = []
    for row in manifest.iter_rows():
        if row["status"] != "imported":
            continue
        record_path = Path(row["record_path"])
        if not record_path.exists():
            continue
        text = display_text(read_text_lossy(record_path))
        items.append(
            CompiledItem(
                archive_id=row["archive_id"],
                title=sanitize_inline(row["title"]),
                source_system=row["source_system"],
                source_kind=row["source_kind"],
                owner_id=row["owner_id"],
                memory_type=row["memory_type"],
                project_hint=sanitize_inline(row["project_hint"]),
                imported_at=row["imported_at"],
                source_mtime=float(row["source_mtime"]),
                source_path=Path(row["source_path"]),
                record_path=record_path,
                snapshot_path=Path(row["snapshot_path"]),
                text=text,
                excerpt=make_excerpt(text),
            )
        )
    return items


def render_readme(config: ArchiveConfig, items: list[CompiledItem]) -> str:
    counts = Counter(item.source_system for item in items)
    return "\n".join(
        [
            "# Compiled Memory Pack",
            "",
            f"- Generated at: `{utc_iso()}`",
            f"- Archive root: `{config.output_root}`",
            f"- Source records: `{len(items)}`",
            f"- Claude Code records: `{counts.get('claude_code', 0)}`",
            f"- Codex records: `{counts.get('codex', 0)}`",
            "- Mode: deterministic local compile, no LLM calls.",
            "",
            "## Files",
            "",
            "- [memory_map.md](memory_map.md): source, owner, type, and project index.",
            "- [recent_changes.md](recent_changes.md): latest imported and latest source-modified records.",
            "- [user_preferences.md](user_preferences.md): likely user preferences and standing instructions.",
            "- [agent_skills.md](agent_skills.md): reusable workflows, runbooks, and skills.",
            "- [project_cases.md](project_cases.md): project-centered experience and context.",
            "- [conflicts.md](conflicts.md): deterministic stale, duplicate, and conflict candidates.",
            "- [bootstrap_context.md](bootstrap_context.md): compact context pack for new agents.",
            "",
            "## Traceability",
            "",
            "Every compiled item links back to the normalized archive record. The archive record links to the redacted source snapshot.",
            "",
        ]
    )


def render_memory_map(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    lines = ["# Memory Map", "", f"Generated at: `{utc_iso()}`", ""]
    lines += render_counter("By Source System", Counter(item.source_system for item in items))
    lines += render_counter("By Memory Type", Counter(item.memory_type for item in items))
    lines += render_counter("By Source Kind", Counter(item.source_kind for item in items))
    lines += render_counter("By Owner", Counter(item.owner_id for item in items))

    projects = Counter(project_key(config, item) for item in items if project_key(config, item))
    lines += render_counter("Project Index", projects, limit=limit)

    lines += ["## Records", ""]
    for item in sorted(items, key=lambda i: (i.source_system, i.memory_type, i.title))[:limit]:
        lines.append(f"- `{item.source_system}` `{item.memory_type}` {source_link(config, item)} — {item.title}")
    lines.append("")
    return "\n".join(lines)


def render_recent_changes(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    lines = ["# Recent Changes", "", "## Latest Imports", ""]
    for item in sorted(items, key=lambda i: i.imported_at, reverse=True)[:limit]:
        lines.extend(render_item(config, item))
    lines += ["## Latest Source Updates", ""]
    for item in sorted(items, key=lambda i: i.source_mtime, reverse=True)[:limit]:
        lines.extend(render_item(config, item))
    return "\n".join(lines)


def render_user_preferences(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    selected = sorted(
        (item for item in items if is_preference_candidate(item)),
        key=lambda item: (-preference_score(item), item.source_system, item.title),
    )[:limit]
    lines = ["# User Preferences", "", "Deterministic candidates extracted from archived records.", ""]
    if not selected:
        lines += ["No preference candidates found.", ""]
        return "\n".join(lines)
    for item in selected:
        lines.extend(render_item(config, item, score=preference_score(item)))
    return "\n".join(lines)


def render_agent_skills(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    selected = sorted(
        (item for item in items if is_skill_candidate(item)),
        key=lambda item: (-skill_score(item), item.source_system, item.title),
    )[:limit]
    lines = ["# Agent Skills", "", "Reusable workflows and runbooks found in the archive.", ""]
    if not selected:
        lines += ["No skill candidates found.", ""]
        return "\n".join(lines)
    for item in selected:
        lines.extend(render_item(config, item, score=skill_score(item)))
    return "\n".join(lines)


def render_project_cases(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    groups: dict[str, list[CompiledItem]] = defaultdict(list)
    for item in items:
        key = project_key(config, item)
        if key:
            groups[key].append(item)

    lines = ["# Project Cases", "", "Project-centered memories grouped by inferred project.", ""]
    if not groups:
        lines += ["No project cases found.", ""]
        return "\n".join(lines)

    for key, group in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:limit]:
        lines += [f"## {sanitize_heading(key)}", ""]
        for item in sorted(group, key=lambda i: (i.memory_type != "agent_case", i.title))[:8]:
            lines.extend(render_item(config, item, compact=True))
    return "\n".join(lines)


def render_conflicts(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    stale = [item for item in items if any(term in item.text.lower() for term in STALE_TERMS)]
    duplicates = duplicate_excerpts(items)
    lines = [
        "# Conflicts",
        "",
        "V1 uses deterministic checks only. Treat these as review candidates, not final judgments.",
        "",
        "## Stale Or Risky Signals",
        "",
    ]
    if stale:
        for item in stale[:limit]:
            lines.extend(render_item(config, item, compact=True))
    else:
        lines += ["No stale or risky signals found by local rules.", ""]

    lines += ["## Duplicate-Looking Excerpts", ""]
    if duplicates:
        for excerpt, dupes in duplicates[:limit]:
            lines += [f"### {sanitize_heading(excerpt[:90])}", ""]
            for item in dupes[:8]:
                lines.append(f"- {source_link(config, item)} — `{item.source_system}` `{item.memory_type}` {item.title}")
            lines.append("")
    else:
        lines += ["No duplicate excerpts found by local rules.", ""]
    return "\n".join(lines)


def render_bootstrap_context(config: ArchiveConfig, items: list[CompiledItem], limit: int) -> str:
    preferences = sorted(
        (item for item in items if is_preference_candidate(item)),
        key=lambda item: (-preference_score(item), item.title),
    )[:limit]
    skills = sorted((item for item in items if is_skill_candidate(item)), key=lambda item: (-skill_score(item), item.title))[
        : max(6, limit // 2)
    ]
    cases = sorted(
        (item for item in items if item.memory_type == "agent_case" or project_key(config, item)),
        key=lambda item: (item.memory_type != "agent_case", item.title),
    )[: max(8, limit // 2)]

    lines = [
        "# Bootstrap Context",
        "",
        "Compact local context pack for starting a new agent session. Generated without LLM calls.",
        "",
        "## Standing Safety",
        "",
        "- Treat Claude Code and Codex source memory directories as read-only.",
        "- Prefer local, source-backed evidence before conclusions.",
        "- Preserve traceability back to archive records and redacted source snapshots.",
        "",
        "## Likely User Preferences",
        "",
    ]
    lines += render_bootstrap_bullets(config, preferences)
    lines += ["## Reusable Agent Workflows", ""]
    lines += render_bootstrap_bullets(config, skills)
    lines += ["## Project Context To Check", ""]
    lines += render_bootstrap_bullets(config, cases)
    return "\n".join(lines)


def render_item(config: ArchiveConfig, item: CompiledItem, *, score: int | None = None, compact: bool = False) -> list[str]:
    title = sanitize_heading(item.title)
    lines = [f"### {title}", ""]
    meta = f"`{item.source_system}` `{item.source_kind}` `{item.memory_type}` owner=`{item.owner_id}`"
    if score is not None:
        meta += f" score=`{score}`"
    lines.append(f"- Meta: {meta}")
    if item.project_hint:
        lines.append(f"- Project: {item.project_hint}")
    lines.append(f"- Source: {source_link(config, item)}")
    if not compact:
        lines.append(f"- Snapshot: `{relative_to_root(config, item.snapshot_path)}`")
    lines.append(f"- Excerpt: {item.excerpt}")
    lines.append("")
    return lines


def render_bootstrap_bullets(config: ArchiveConfig, items: list[CompiledItem]) -> list[str]:
    if not items:
        return ["- No candidates found.", ""]
    lines: list[str] = []
    for item in items:
        project = f" Project: {item.project_hint}." if item.project_hint else ""
        lines.append(f"- {item.excerpt}{project} Source: {source_link(config, item)}")
    lines.append("")
    return lines


def render_counter(title: str, counter: Counter, *, limit: int = 40) -> list[str]:
    lines = [f"## {title}", ""]
    if not counter:
        return lines + ["No entries.", ""]
    lines += ["| Key | Count |", "|---|---:|"]
    for key, count in counter.most_common(limit):
        lines.append(f"| {sanitize_table(str(key))} | {count} |")
    lines.append("")
    return lines


def write_file(path: Path, text: str) -> Path:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def display_text(record_text: str) -> str:
    marker = "## Redacted Source"
    marker_index = record_text.find(marker)
    if marker_index >= 0:
        after_heading = record_text.find("\n", marker_index)
        if after_heading >= 0:
            return record_text[after_heading + 1 :].strip()
    if record_text.startswith("---\n"):
        end = record_text.find("\n---\n", 4)
        if end >= 0:
            return record_text[end + 5 :].strip()
    return record_text


def make_excerpt(text: str, *, max_lines: int = 4, max_chars: int = 520) -> str:
    lines: list[str] = []
    in_frontmatter = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not line:
            continue
        if line.startswith(("allowed-tools:", "metadata:", "argument-hint:", "user-invocable:")):
            continue
        if line in {"```", "```bash", "```text", "```toml", "```json"}:
            continue
        cleaned = sanitize_inline(line)
        if cleaned:
            lines.append(cleaned)
        if len(lines) >= max_lines:
            break
    if not lines:
        lines = [sanitize_inline(text[:max_chars])]
    excerpt = " / ".join(lines)
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1].rstrip() + "..."
    return excerpt


def preference_score(item: CompiledItem) -> int:
    haystack = f"{item.title}\n{item.project_hint}\n{item.text}".lower()
    score = 0
    if item.owner_id not in {"codex", "claude-code"}:
        score += 3
    if item.source_kind in {"summary", "memory_index", "raw_memory", "ad_hoc_note", "claude_md_user", "claude_md_project"}:
        score += 2
    for term in PREFERENCE_TERMS:
        score += haystack.count(term.lower()) * 2
    return score


def is_preference_candidate(item: CompiledItem) -> bool:
    if item.source_kind == "raw_memory":
        return False
    haystack = f"{item.title}\n{item.project_hint}\n{item.text}".lower()
    explicit = any(
        marker in haystack
        for marker in (
            "user profile",
            "user preferences",
            "user preference",
            "用户偏好",
            "偏好",
            "user prefers",
            "the user prefers",
            "用户喜欢",
            "用户要求",
        )
    )
    if item.source_kind in {"summary", "ad_hoc_note", "claude_md_user"}:
        return preference_score(item) > 0
    return False


def skill_score(item: CompiledItem) -> int:
    haystack = f"{item.title}\n{item.project_hint}\n{item.text}".lower()
    score = 0
    if item.memory_type == "agent_skill":
        score += 20
    if item.source_kind == "skill":
        score += 12
    for term in SKILL_TERMS:
        score += haystack.count(term.lower())
    return score


def is_skill_candidate(item: CompiledItem) -> bool:
    if item.source_kind == "raw_memory":
        return False
    if item.memory_type == "agent_skill" or item.source_kind == "skill":
        return True
    haystack = f"{item.title}\n{item.project_hint}\n{item.text}".lower()
    explicit = any(marker in haystack for marker in ("runbook", "workflow", "agent_skill", "skill:", "## procedure"))
    if item.source_kind in {"memory_index", "summary"}:
        return explicit and skill_score(item) >= 8
    if item.source_kind == "rollout_summary":
        return False
    return explicit and skill_score(item) >= 8


def project_key(config: ArchiveConfig, item: CompiledItem) -> str:
    text = f"{item.project_hint}\n{item.source_path}\n{item.title}"
    for root in config.repo_roots:
        root_text = str(root.expanduser())
        match = re.search(rf"{re.escape(root_text)}/([A-Za-z0-9_.-]+)", text)
        if match:
            return match.group(1)
    if item.project_hint and item.project_hint not in {str(root.expanduser()) for root in config.repo_roots}:
        return item.project_hint.split(" — ")[0].strip()
    if item.source_kind in {"claude_md_project", "rule", "skill"}:
        parts = list(item.source_path.parts)
        for root in config.repo_roots:
            root_parts = list(root.expanduser().parts)
            for index in range(len(parts) - len(root_parts) + 1):
                if parts[index : index + len(root_parts)] == root_parts and index + len(root_parts) < len(parts):
                    return parts[index + len(root_parts)]
    return ""


def duplicate_excerpts(items: list[CompiledItem]) -> list[tuple[str, list[CompiledItem]]]:
    groups: dict[str, list[CompiledItem]] = defaultdict(list)
    for item in items:
        key = normalize_excerpt(item.excerpt)
        if key:
            groups[key].append(item)
    duplicates = [(items_for_key[0].excerpt, items_for_key) for items_for_key in groups.values() if len(items_for_key) > 1]
    return sorted(duplicates, key=lambda pair: -len(pair[1]))


def normalize_excerpt(value: str) -> str:
    value = re.sub(r"`[^`]+`", "", value.lower())
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    value = " ".join(value.split())
    return value if len(value) >= 40 else ""


def source_link(config: ArchiveConfig, item: CompiledItem) -> str:
    rel = relative_from_compiled(config, item.record_path)
    return f"[`{item.archive_id}`]({rel})"


def relative_from_compiled(config: ArchiveConfig, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(config.output_root.resolve())
        return "../" + rel.as_posix()
    except ValueError:
        return path.as_posix()


def relative_to_root(config: ArchiveConfig, path: Path) -> str:
    try:
        return path.resolve().relative_to(config.output_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sanitize_inline(value: str) -> str:
    value = " ".join(value.replace("|", "\\|").split())
    value = STOCK_CONTRAST_PATTERN.sub("stock AI contrast phrasing", value)
    value = value.replace(STOCK_YI_DAO_PHRASE, "a stock AI-sounding phrase")
    return value


def sanitize_heading(value: str) -> str:
    value = sanitize_inline(value).strip("# ")
    return value or "Untitled"


def sanitize_table(value: str) -> str:
    return sanitize_inline(value).replace("\n", " ")
