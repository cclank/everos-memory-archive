from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from archive_memory.config import ArchiveConfig
from archive_memory.utils import read_text_lossy, slugify


DEFAULT_COMPILED_FILES = (
    "bootstrap_context.md",
    "user_preferences.md",
    "agent_skills.md",
    "project_cases.md",
    "memory_map.md",
    "recent_changes.md",
    "conflicts.md",
)


@dataclass(frozen=True)
class EverOSImportResult:
    session_id: str
    app_id: str
    project_id: str
    user_id: str
    message_count: int
    add_status: str
    flush_status: str | None
    base_url: str


def import_memory_pack_to_everos(
    config: ArchiveConfig,
    *,
    base_url: str = "http://127.0.0.1:8000",
    app_id: str = "agent-memory-archive",
    project_id: str = "codex-claude-code",
    user_id: str | None = None,
    session_id: str | None = None,
    files: list[Path] | None = None,
    flush: bool = True,
) -> EverOSImportResult:
    compiled_dir = config.output_root / "compiled"
    selected = files or [compiled_dir / name for name in DEFAULT_COMPILED_FILES]
    existing = [path for path in selected if path.exists()]
    if not existing:
        raise RuntimeError(f"no compiled Memory Pack files found under {compiled_dir}")

    owner = user_id or slugify(config.user_id, "user")
    session = session_id or f"archive-import-{int(time.time())}"
    now_ms = int(time.time() * 1000)
    messages = [
        {
            "sender_id": owner,
            "role": "user",
            "timestamp": now_ms + index,
            "content": render_import_message(path, compiled_dir),
        }
        for index, path in enumerate(existing)
    ]

    add_payload = {
        "session_id": session,
        "app_id": app_id,
        "project_id": project_id,
        "messages": messages,
    }
    add_response = post_json(base_url, "/api/v1/memory/add", add_payload)
    add_status = str(add_response.get("data", {}).get("status", "unknown"))

    flush_status: str | None = None
    if flush:
        flush_response = post_json(
            base_url,
            "/api/v1/memory/flush",
            {"session_id": session, "app_id": app_id, "project_id": project_id},
        )
        flush_status = str(flush_response.get("data", {}).get("status", "unknown"))

    return EverOSImportResult(
        session_id=session,
        app_id=app_id,
        project_id=project_id,
        user_id=owner,
        message_count=len(messages),
        add_status=add_status,
        flush_status=flush_status,
        base_url=base_url.rstrip("/"),
    )


def render_import_message(path: Path, compiled_dir: Path) -> str:
    try:
        rel = path.resolve().relative_to(compiled_dir.resolve()).as_posix()
    except ValueError:
        rel = path.name
    return "\n".join(
        [
            f"# Imported Memory Pack File: {rel}",
            "",
            "Source: everos-memory-archive compiled Memory Pack.",
            "Use this as source-backed context from archived Codex and Claude Code memories.",
            "",
            read_text_lossy(path).strip(),
            "",
        ]
    )


def post_json(base_url: str, path: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"EverOS request failed: {exc.code} {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach EverOS server at {base_url}: {exc}") from exc
