from __future__ import annotations

from pathlib import Path

from archive_memory.models import SourceItem
from archive_memory.redactor import is_sensitive_path
from archive_memory.utils import sha256_file


def build_item(source_system: str, source_kind: str, path: Path, root: Path) -> SourceItem | None:
    if path.is_symlink() or not path.exists() or not path.is_file() or is_sensitive_path(path):
        return None
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        rel = resolved_path.relative_to(resolved_root).as_posix()
    except (FileNotFoundError, ValueError):
        return None
    if is_sensitive_path(resolved_path):
        return None
    stat = resolved_path.stat()
    return SourceItem(
        source_system=source_system,
        source_kind=source_kind,
        source_path=path,
        source_root=root,
        relative_path=rel,
        size=stat.st_size,
        mtime=stat.st_mtime,
        sha256=sha256_file(resolved_path),
    )
