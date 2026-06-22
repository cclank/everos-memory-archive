from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArchiveConfig:
    home: Path = field(default_factory=lambda: Path.home())
    claude_root: Path = field(default_factory=lambda: Path.home() / ".claude")
    codex_memory_root: Path = field(default_factory=lambda: Path.home() / ".codex" / "memories")
    repo_roots: tuple[Path, ...] = field(default_factory=lambda: (Path.home() / "code",))
    output_root: Path = field(default_factory=lambda: Path.home() / ".everos" / "agent_memory_archive")
    user_id: str = field(default_factory=lambda: os.getenv("USER") or "user")
    claude_agent_id: str = "claude-code"
    codex_agent_id: str = "codex"

    @property
    def protected_roots(self) -> list[Path]:
        return [self.claude_root, self.codex_memory_root, self.home / ".codex"]

    @property
    def unified_root(self) -> Path:
        return self.output_root / "unified_index"

    @property
    def manifest_path(self) -> Path:
        return self.unified_root / "manifest.sqlite"

    def source_archive_root(self, source_system: str) -> Path:
        return self.output_root / source_system


def load_config(path: Path | None = None) -> ArchiveConfig:
    if path is None:
        return ArchiveConfig()

    raw = _parse_simple_toml(path.read_text(encoding="utf-8"))
    sources = raw.get("sources", {})
    everos = raw.get("everos", {})
    agents = everos.get("agents", {})

    repo_roots = tuple(Path(p).expanduser() for p in sources.get("repo_roots", [])) or ArchiveConfig().repo_roots

    return ArchiveConfig(
        claude_root=Path(sources.get("claude_code_root", ArchiveConfig().claude_root)).expanduser(),
        codex_memory_root=Path(sources.get("codex_memory_root", ArchiveConfig().codex_memory_root)).expanduser(),
        repo_roots=repo_roots,
        output_root=Path(everos.get("output_root", ArchiveConfig().output_root)).expanduser(),
        user_id=everos.get("user_id", ArchiveConfig().user_id),
        claude_agent_id=agents.get("claude_code", "claude-code"),
        codex_agent_id=agents.get("codex", "codex"),
    )


def _parse_simple_toml(text: str) -> dict[str, Any]:
    """Parse the small config shape used by this tool.

    This intentionally supports only section headers, quoted strings, and
    arrays of quoted strings so the CLI works on Python 3.9 without deps.
    """

    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current = root
            for part in section.split("."):
                current = current.setdefault(part, {})
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        current[key.strip()] = _parse_value(value.strip())
    return root


def _parse_value(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(part.strip()) for part in inner.split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value
