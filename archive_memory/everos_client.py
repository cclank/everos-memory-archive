from __future__ import annotations

import ipaddress
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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

EVEROS_MODEL_BASE_URL_KEYS = (
    "EVEROS_LLM__BASE_URL",
    "EVEROS_MULTIMODAL__BASE_URL",
    "EVEROS_EMBEDDING__BASE_URL",
    "EVEROS_RERANK__BASE_URL",
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
    everos_env_file: Path | None = None,
) -> EverOSImportResult:
    require_loopback_url(base_url, label="EverOS API")
    require_local_everos_model_endpoints(everos_env_file)

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


def require_local_everos_model_endpoints(env_file: Path | None = None) -> None:
    """Fail unless EverOS model endpoints are provably local.

    The importer posts private Memory Pack contents into EverOS. During
    ``/add`` or ``/flush``, EverOS may call its configured LLM, embedding,
    and rerank endpoints with that content. A loopback EverOS API is not
    enough: the model endpoints must also be loopback URLs.
    """
    values = _load_everos_endpoint_env(env_file)
    missing = [key for key in EVEROS_MODEL_BASE_URL_KEYS if not values.get(key)]
    if missing:
        hint = (
            "pass --everos-env-file /path/to/everos-local.env or export "
            + ", ".join(EVEROS_MODEL_BASE_URL_KEYS)
        )
        raise RuntimeError(
            "cannot prove EverOS model endpoints are local; refusing to import "
            f"private Memory Pack contents (missing: {', '.join(missing)}; {hint})"
        )
    for key in EVEROS_MODEL_BASE_URL_KEYS:
        require_loopback_url(values[key], label=key)


def _load_everos_endpoint_env(env_file: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    resolved = _resolve_env_file(env_file)
    if resolved is not None:
        values.update(_read_dotenv(resolved))
    for key in EVEROS_MODEL_BASE_URL_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def _resolve_env_file(env_file: Path | None) -> Path | None:
    candidates: list[Path] = []
    if env_file is not None:
        candidates.append(env_file.expanduser())
    elif os.environ.get("EVEROS_MEMORY_ARCHIVE_EVEROS_ENV_FILE"):
        candidates.append(Path(os.environ["EVEROS_MEMORY_ARCHIVE_EVEROS_ENV_FILE"]).expanduser())
    else:
        xdg_home = Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()
        candidates.extend(
            [
                Path.cwd() / ".env",
                xdg_home / "everos" / ".env",
                Path("~/.everos/.env").expanduser(),
            ]
        )

    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in EVEROS_MODEL_BASE_URL_KEYS:
            continue
        values[key] = _strip_env_value(value)
    return values


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def require_loopback_url(url: str, *, label: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host:
        raise RuntimeError(f"{label} must be an http(s) loopback URL")
    if _is_loopback_host(host):
        return
    raise RuntimeError(
        f"{label} points to non-local host {host!r}; refusing to send private memory contents"
    )


def _is_loopback_host(host: str) -> bool:
    lowered = host.lower()
    if lowered == "localhost":
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False
