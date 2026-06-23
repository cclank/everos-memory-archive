from __future__ import annotations

import hashlib
import os
import re
import tempfile
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


def ensure_under(path: Path, root: Path, *, context: str = "path") -> Path:
    resolved = path.expanduser().resolve()
    resolved_root = root.expanduser().resolve()
    if not is_relative_to(resolved, resolved_root):
        raise RuntimeError(f"{context} must stay under archive root: {resolved}")
    return resolved


def ensure_safe_output_path(
    path: Path,
    output_root: Path,
    forbidden_roots: list[Path],
    *,
    context: str = "output path",
) -> Path:
    path = path.expanduser()
    output_root = output_root.expanduser()
    ensure_not_under(output_root, forbidden_roots)
    path.parent.mkdir(parents=True, exist_ok=True)

    resolved_root = output_root.resolve()
    resolved_parent = path.parent.resolve()
    if not is_relative_to(resolved_parent, resolved_root):
        raise RuntimeError(f"{context} parent must stay under archive root: {resolved_parent}")
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"{context} must not be a symlink: {path}")

    resolved_path = path.resolve() if path.exists() else resolved_parent / path.name
    if not is_relative_to(resolved_path, resolved_root):
        raise RuntimeError(f"{context} must stay under archive root: {resolved_path}")
    for root in forbidden_roots:
        if is_relative_to(resolved_path, root):
            raise RuntimeError(f"{context} must not be inside protected source root: {resolved_path}")
    return path


def safe_write_bytes(
    path: Path,
    payload: bytes,
    output_root: Path,
    forbidden_roots: list[Path],
    *,
    context: str = "output path",
) -> Path:
    path = ensure_safe_output_path(path, output_root, forbidden_roots, context=context)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        if path.exists() and path.is_symlink():
            raise RuntimeError(f"{context} must not be a symlink: {path}")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return path


def safe_write_text(
    path: Path,
    text: str,
    output_root: Path,
    forbidden_roots: list[Path],
    *,
    context: str = "output path",
) -> Path:
    return safe_write_bytes(path, text.encode("utf-8"), output_root, forbidden_roots, context=context)


def resolve_existing_archive_file(
    path: Path,
    output_root: Path,
    forbidden_roots: list[Path],
    *,
    context: str = "archive file",
) -> Path:
    path = path.expanduser()
    if path.is_symlink():
        raise RuntimeError(f"{context} must not be a symlink: {path}")
    if not path.exists():
        raise RuntimeError(f"{context} does not exist: {path}")
    if not path.is_file():
        raise RuntimeError(f"{context} must be a file: {path}")
    resolved = ensure_under(path, output_root, context=context)
    for root in forbidden_roots:
        if is_relative_to(resolved, root):
            raise RuntimeError(f"{context} must not be inside protected source root: {resolved}")
    return resolved


def read_text_lossy(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
