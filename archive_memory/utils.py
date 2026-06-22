from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else datetime.now(timezone.utc)
    return dt.isoformat(timespec="seconds")


def safe_fragment(value: str) -> str:
    value = value.strip().replace("\\", "/")
    value = re.sub(r"^/+", "", value)
    value = re.sub(r"[^A-Za-z0-9._/\-]+", "-", value)
    value = re.sub(r"/+", "/", value)
    value = value.replace("../", "__/")
    return value or "root"


def slugify(value: str, fallback: str = "memory") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or fallback


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def ensure_not_under(path: Path, forbidden_roots: list[Path]) -> None:
    resolved = path.resolve()
    for root in forbidden_roots:
        if is_relative_to(resolved, root):
            raise RuntimeError(f"refusing to write under protected source root: {resolved}")


def read_text_lossy(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
