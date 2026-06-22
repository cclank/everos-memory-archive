from __future__ import annotations

import sqlite3
from pathlib import Path

from archive_memory.models import Classification, SourceItem


SCHEMA = """
create table if not exists imports (
  archive_id text primary key,
  source_system text not null,
  source_kind text not null,
  source_path text not null,
  source_hash text not null,
  source_mtime real not null,
  source_size integer not null,
  owner_type text not null,
  owner_id text not null,
  memory_type text not null,
  project_hint text not null,
  title text not null,
  snapshot_path text not null,
  record_path text not null,
  imported_at text not null,
  status text not null,
  error text
);

create index if not exists idx_imports_source_path on imports(source_path);
create index if not exists idx_imports_source_hash on imports(source_hash);
create index if not exists idx_imports_imported_at on imports(imported_at);
"""


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def has_success(self, source_path: Path, source_hash: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "select 1 from imports where source_path = ? and source_hash = ? and status = 'imported' limit 1",
                (source_path.as_posix(), source_hash),
            ).fetchone()
        return row is not None

    def latest_success_for_path(self, source_path: Path) -> sqlite3.Row | None:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """
                select * from imports
                where source_path = ? and status = 'imported'
                order by imported_at desc
                limit 1
                """,
                (source_path.as_posix(),),
            ).fetchone()

    def latest_success_for_hash(self, source_hash: str, source_system: str | None = None) -> sqlite3.Row | None:
        params: list[str] = [source_hash]
        clause = "source_hash = ? and status = 'imported'"
        if source_system:
            clause += " and source_system = ?"
            params.append(source_system)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                f"""
                select * from imports
                where {clause}
                order by imported_at desc
                limit 1
                """,
                params,
            ).fetchone()

    def latest_success_paths(self, source_systems: set[str] | None = None) -> dict[str, sqlite3.Row]:
        params: list[str] = []
        system_clause = ""
        if source_systems:
            placeholders = ", ".join("?" for _ in source_systems)
            system_clause = f" and source_system in ({placeholders})"
            params.extend(sorted(source_systems))
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                select i.*
                from imports i
                join (
                  select source_path, max(imported_at) as max_imported_at
                  from imports
                  where status = 'imported'{system_clause}
                  group by source_path
                ) latest
                  on i.source_path = latest.source_path
                 and i.imported_at = latest.max_imported_at
                where i.status = 'imported'{system_clause.replace("source_system", "i.source_system")}
                """,
                params + params,
            ).fetchall()
        return {row["source_path"]: row for row in rows}

    def upsert(
        self,
        *,
        archive_id: str,
        item: SourceItem,
        classification: Classification,
        snapshot_path: Path,
        record_path: Path,
        imported_at: str,
        status: str,
        error: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert or replace into imports (
                  archive_id, source_system, source_kind, source_path, source_hash,
                  source_mtime, source_size, owner_type, owner_id, memory_type,
                  project_hint, title, snapshot_path, record_path, imported_at,
                  status, error
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive_id,
                    item.source_system,
                    item.source_kind,
                    item.source_path.as_posix(),
                    item.sha256,
                    item.mtime,
                    item.size,
                    classification.owner_type,
                    classification.owner_id,
                    classification.memory_type,
                    classification.project_hint,
                    classification.title,
                    snapshot_path.as_posix(),
                    record_path.as_posix(),
                    imported_at,
                    status,
                    error,
                ),
            )
            conn.commit()

    def latest_report_rows(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "select * from imports order by imported_at desc limit ?",
                (limit,),
            ).fetchall()
        return rows

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("select status, count(*) from imports group by status").fetchall()
        return {status: count for status, count in rows}

    def grouped_counts(self, field: str) -> dict[str, int]:
        allowed = {
            "source_system",
            "source_kind",
            "owner_type",
            "owner_id",
            "memory_type",
            "status",
        }
        if field not in allowed:
            raise ValueError(f"unsupported count field: {field}")
        with self.connect() as conn:
            rows = conn.execute(
                f"select {field}, count(*) from imports group by {field} order by {field}"
            ).fetchall()
        return {str(key): count for key, count in rows}

    def iter_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("select * from imports order by source_system, source_kind, source_path").fetchall()

    def get(self, archive_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("select * from imports where archive_id = ?", (archive_id,)).fetchone()
