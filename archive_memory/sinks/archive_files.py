from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from archive_memory.classifier import classify
from archive_memory.config import ArchiveConfig
from archive_memory.manifest import Manifest
from archive_memory.models import ImportResult, SourceItem
from archive_memory.redactor import redact_text
from archive_memory.renderer import render_record
from archive_memory.utils import (
    ensure_not_under,
    ensure_safe_output_path,
    read_text_lossy,
    safe_fragment,
    safe_write_text,
    slugify,
    utc_iso,
)


class ArchiveFileSink:
    def __init__(self, config: ArchiveConfig, *, keep_versions: bool = False) -> None:
        self.config = config
        self.keep_versions = keep_versions
        self.root = config.output_root.expanduser()
        ensure_not_under(self.root, config.protected_roots)
        ensure_safe_output_path(config.manifest_path, self.root, config.protected_roots, context="manifest path")
        self.manifest = Manifest(config.manifest_path)

    def import_items(
        self,
        items: list[SourceItem],
        *,
        incremental: bool = True,
        limit: int | None = None,
        write_report: bool = True,
        report_name: str = "import",
        report_extra: dict | None = None,
    ) -> list[ImportResult]:
        selected = items[:limit] if limit else items
        results: list[ImportResult] = []
        for item in selected:
            if incremental and self.should_skip(item):
                continue
            results.append(self.import_item(item))
        if write_report:
            self.write_report(results, report_name=report_name, extra=report_extra)
        return results

    def should_skip(self, item: SourceItem) -> bool:
        if not self.manifest.has_success(item.source_path, item.sha256):
            return False
        if not self.keep_versions:
            return True
        return self.snapshot_path(item).exists() and self.latest_snapshot_path(item).exists()

    def import_item(self, item: SourceItem) -> ImportResult:
        original = read_text_lossy(item.source_path)
        redacted = redact_text(original)
        classification = classify(item, self.config, text=redacted)
        imported_at = utc_iso()
        archive_id = self.archive_id(item)
        snapshot_path = self.snapshot_path(item)
        record_path = self.record_path(item, archive_id, classification)

        try:
            safe_write_text(
                snapshot_path,
                redacted,
                self.root,
                self.config.protected_roots,
                context="snapshot path",
            )
            if self.keep_versions:
                latest_path = self.latest_snapshot_path(item)
                safe_write_text(
                    latest_path,
                    redacted,
                    self.root,
                    self.config.protected_roots,
                    context="latest snapshot path",
                )

            record = render_record(
                archive_id=archive_id,
                item=item,
                classification=classification,
                redacted_text=redacted,
                snapshot_path=snapshot_path,
                output_root=self.root,
                imported_at=imported_at,
            )
            safe_write_text(
                record_path,
                record,
                self.root,
                self.config.protected_roots,
                context="record path",
            )
            status = "imported"
            error = None
        except Exception as exc:  # noqa: BLE001 - persisted for import audit.
            status = "failed"
            error = str(exc)

        self.manifest.upsert(
            archive_id=archive_id,
            item=item,
            classification=classification,
            snapshot_path=snapshot_path,
            record_path=record_path,
            imported_at=imported_at,
            status=status,
            error=error,
        )
        return ImportResult(archive_id, item, classification, snapshot_path, record_path, status, error)

    def archive_id(self, item: SourceItem) -> str:
        path_hash = hashlib.sha256(item.source_path.as_posix().encode("utf-8")).hexdigest()[:12]
        return f"{item.source_system}__{item.source_kind}__{path_hash}__{item.sha256[:16]}"

    def snapshot_path(self, item: SourceItem) -> Path:
        if self.keep_versions:
            return self.version_snapshot_path(item)
        return self.latest_snapshot_path(item)

    def latest_snapshot_path(self, item: SourceItem) -> Path:
        rel = safe_fragment(item.relative_path)
        return self.config.source_archive_root(item.source_system) / "sources" / rel

    def version_snapshot_path(self, item: SourceItem) -> Path:
        rel = Path(safe_fragment(item.relative_path))
        return (
            self.config.source_archive_root(item.source_system)
            / "sources"
            / rel.parent
            / f"{rel.name}.versions"
            / f"{item.sha256}.md"
        )

    def record_path(self, item: SourceItem, archive_id: str, classification) -> Path:
        owner = slugify(classification.owner_id, "owner")
        memory = slugify(classification.memory_type, "memory")
        source_root = self.config.source_archive_root(item.source_system)
        if classification.owner_type == "user":
            return source_root / "records" / "user" / owner / memory / f"{archive_id}.md"
        return source_root / "records" / "agents" / owner / memory / f"{archive_id}.md"

    def write_report(
        self,
        results: list[ImportResult],
        *,
        report_name: str = "import",
        extra: dict | None = None,
    ) -> Path:
        reports_dir = self.config.unified_root / "reports"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_report_name = slugify(report_name, "report")
        path = reports_dir / f"{safe_report_name}-{stamp}.json"
        counts = Counter(result.status for result in results)
        payload = {
            "generated_at": utc_iso(),
            "report_name": safe_report_name,
            "output_root": self.root.as_posix(),
            "unified_root": self.config.unified_root.as_posix(),
            "keep_versions": self.keep_versions,
            "counts": dict(counts),
            "items": [
                {
                    "archive_id": result.archive_id,
                    "status": result.status,
                    "source_system": result.source_item.source_system,
                    "source_kind": result.source_item.source_kind,
                    "source_path": result.source_item.source_path.as_posix(),
                    "record_path": result.record_path.as_posix(),
                    "snapshot_path": result.snapshot_path.as_posix(),
                    "error": result.error,
                }
                for result in results
            ],
        }
        if extra:
            payload.update(extra)
        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        safe_write_text(
            path,
            payload_text,
            self.root,
            self.config.protected_roots,
            context="report path",
        )
        latest = reports_dir / "latest.json"
        safe_write_text(
            latest,
            payload_text,
            self.root,
            self.config.protected_roots,
            context="latest report path",
        )
        return path
