from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceItem:
    source_system: str
    source_kind: str
    source_path: Path
    source_root: Path
    relative_path: str
    size: int
    mtime: float
    sha256: str


@dataclass(frozen=True)
class Classification:
    owner_type: str
    owner_id: str
    memory_type: str
    project_hint: str
    title: str


@dataclass(frozen=True)
class ImportResult:
    archive_id: str
    source_item: SourceItem
    classification: Classification
    snapshot_path: Path
    record_path: Path
    status: str
    error: str | None = None
