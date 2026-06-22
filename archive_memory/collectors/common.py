from __future__ import annotations

from pathlib import Path

from archive_memory.models import SourceItem
from archive_memory.redactor import is_sensitive_path
from archive_memory.utils import sha256_file


def build_item(source_system: str, source_kind: str, path: Path, root: Path) -> SourceItem | None:
    if not path.exists() or not path.is_file() or is_sensitive_path(path):
        return None
    stat = path.stat()
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = path.name
    return SourceItem(
        source_system=source_system,
        source_kind=source_kind,
        source_path=path,
        source_root=root,
        relative_path=rel,
        size=stat.st_size,
        mtime=stat.st_mtime,
        sha256=sha256_file(path),
    )
