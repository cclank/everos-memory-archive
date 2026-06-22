from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archive_memory.config import ArchiveConfig
from archive_memory.manifest import Manifest
from archive_memory.utils import read_text_lossy


@dataclass(frozen=True)
class SearchHit:
    archive_id: str
    title: str
    score: int
    source_system: str
    source_kind: str
    owner_id: str
    memory_type: str
    record_path: str
    snippet: str


def search_archive(
    config: ArchiveConfig,
    query: str,
    *,
    source: str | None = None,
    owner: str | None = None,
    memory_type: str | None = None,
    limit: int = 10,
) -> list[SearchHit]:
    terms = [term.lower() for term in query.split() if term.strip()]
    if not terms:
        return []

    manifest = Manifest(config.manifest_path)
    hits: list[SearchHit] = []
    for row in manifest.iter_rows():
        if source and row["source_system"] != source:
            continue
        if owner and row["owner_id"] != owner:
            continue
        if memory_type and row["memory_type"] != memory_type:
            continue

        path = Path(row["record_path"])
        if not path.exists():
            continue
        text = read_text_lossy(path)
        display_text = _display_text(text)
        haystack = "\n".join(
            [
                row["title"],
                row["source_system"],
                row["source_kind"],
                row["owner_id"],
                row["memory_type"],
                row["project_hint"],
                display_text,
            ]
        ).lower()
        score = _score(haystack, terms)
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                archive_id=row["archive_id"],
                title=row["title"],
                score=score,
                source_system=row["source_system"],
                source_kind=row["source_kind"],
                owner_id=row["owner_id"],
                memory_type=row["memory_type"],
                record_path=row["record_path"],
                snippet=_snippet(display_text, terms),
            )
        )
    return sorted(hits, key=lambda hit: (-hit.score, hit.title))[:limit]


def _score(haystack: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        count = haystack.count(term)
        score += count
        if count:
            score += 10
    return score


def _snippet(text: str, terms: list[str], radius: int = 120) -> str:
    lower = text.lower()
    first = min((lower.find(term) for term in terms if lower.find(term) >= 0), default=0)
    start = max(0, first - radius)
    end = min(len(text), first + radius)
    snippet = text[start:end].replace("\n", " ")
    return " ".join(snippet.split())


def _display_text(record_text: str) -> str:
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
