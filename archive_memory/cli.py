from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from archive_memory.compiler import compile_archive
from archive_memory.config import load_config
from archive_memory.everos_client import import_memory_pack_to_everos
from archive_memory.manifest import Manifest
from archive_memory.models import SourceItem
from archive_memory.scanner import parse_sources, scan
from archive_memory.search import search_archive
from archive_memory.sinks.archive_files import ArchiveFileSink
from archive_memory.verify import verify_archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="everos-memory-archive")
    parser.add_argument("--config", type=Path, help="Optional TOML config file.")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan source memory files without writing.")
    scan_p.add_argument("--source", default="all", help="all, claude, codex, or comma-separated.")
    scan_p.add_argument("--dry-run", action="store_true", help="Alias for scan preview; no writes happen.")
    scan_p.add_argument("--json", action="store_true", help="Print JSON.")

    import_p = sub.add_parser("import", help="Import memories into the archive.")
    import_p.add_argument("--source", default="all", help="all, claude, codex, or comma-separated.")
    import_p.add_argument("--incremental", action="store_true", default=True, help="Skip unchanged files.")
    import_p.add_argument("--no-incremental", dest="incremental", action="store_false")
    import_p.add_argument("--keep-versions", action="store_true", help="Store immutable source snapshots by hash.")
    import_p.add_argument("--limit", type=int, help="Import at most N items.")

    sync_p = sub.add_parser("sync", help="Incrementally archive memories, keep versions, and verify.")
    sync_p.add_argument("--source", default="all", help="all, claude, codex, or comma-separated.")
    sync_p.add_argument("--limit", type=int, help="Sync at most N scanned items.")
    sync_p.add_argument("--keep-versions", dest="keep_versions", action="store_true", default=True)
    sync_p.add_argument("--no-keep-versions", dest="keep_versions", action="store_false")
    sync_p.add_argument("--no-secret-scan", action="store_true", help="Skip redaction verification scan.")
    sync_p.add_argument("--json", action="store_true")

    backup_p = sub.add_parser("backup", help="One-click sync, compile, and verify.")
    backup_p.add_argument("--source", default="claude,codex", help="all, claude, codex, or comma-separated.")
    backup_p.add_argument("--limit", type=int, help="Back up at most N scanned items.")
    backup_p.add_argument("--no-compile", action="store_true", help="Skip Memory Pack compilation.")
    backup_p.add_argument("--no-secret-scan", action="store_true", help="Skip redaction verification scan.")
    backup_p.add_argument("--max-items", type=int, default=40, help="Maximum items per compiled section.")
    backup_p.add_argument("--bootstrap-limit", type=int, default=24, help="Maximum candidates in bootstrap context.")
    backup_p.add_argument("--json", action="store_true")

    compile_p = sub.add_parser("compile", help="Compile archived records into a local Memory Pack.")
    compile_p.add_argument("--max-items", type=int, default=40, help="Maximum items per compiled section.")
    compile_p.add_argument("--bootstrap-limit", type=int, default=24, help="Maximum candidates in bootstrap context.")
    compile_p.add_argument("--json", action="store_true")

    everos_p = sub.add_parser("everos-import", help="Import the compiled Memory Pack into a running EverOS server.")
    everos_p.add_argument("--base-url", default="http://127.0.0.1:8000", help="EverOS server base URL.")
    everos_p.add_argument("--app-id", default="agent-memory-archive", help="EverOS app_id scope.")
    everos_p.add_argument("--project-id", default="codex-claude-code", help="EverOS project_id scope.")
    everos_p.add_argument("--user-id", help="EverOS user_id / sender_id. Defaults to config user_id.")
    everos_p.add_argument("--session-id", help="EverOS session_id. Defaults to archive-import-<timestamp>.")
    everos_p.add_argument("--file", action="append", type=Path, dest="files", help="Compiled Markdown file to import.")
    everos_p.add_argument("--no-flush", action="store_true", help="Skip /api/v1/memory/flush after /add.")
    everos_p.add_argument("--json", action="store_true")

    report_p = sub.add_parser("report", help="Show import report.")
    report_p.add_argument("--latest", action="store_true", help="Show latest manifest counts and rows.")

    show_p = sub.add_parser("show", help="Show one archived record by id.")
    show_p.add_argument("--id", required=True, help="Archive id.")

    search_p = sub.add_parser("search", help="Search archived records.")
    search_p.add_argument("query", help="Keyword query.")
    search_p.add_argument("--source", choices=["claude_code", "codex"], help="Filter source system.")
    search_p.add_argument("--owner", help="Filter owner id, e.g. codex or claude-code.")
    search_p.add_argument("--memory-type", help="Filter memory type, e.g. agent_case.")
    search_p.add_argument("--limit", type=int, default=10)
    search_p.add_argument("--json", action="store_true")

    verify_p = sub.add_parser("verify", help="Verify archive integrity and safety.")
    verify_p.add_argument("--no-secret-scan", action="store_true", help="Skip redaction verification scan.")

    sub.add_parser("stats", help="Show archive statistics.")

    init_p = sub.add_parser("init-config", help="Write an example config file.")
    init_p.add_argument("--path", type=Path, default=Path("configs/local.toml"))
    init_p.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command == "scan":
        return cmd_scan(args, config)
    if args.command == "import":
        return cmd_import(args, config)
    if args.command == "sync":
        return cmd_sync(args, config)
    if args.command == "backup":
        return cmd_backup(args, config)
    if args.command == "compile":
        return cmd_compile(args, config)
    if args.command == "everos-import":
        return cmd_everos_import(args, config)
    if args.command == "report":
        return cmd_report(args, config)
    if args.command == "show":
        return cmd_show(args, config)
    if args.command == "search":
        return cmd_search(args, config)
    if args.command == "verify":
        return cmd_verify(args, config)
    if args.command == "stats":
        return cmd_stats(args, config)
    if args.command == "init-config":
        return cmd_init_config(args, config)
    parser.error("unknown command")
    return 2


def cmd_scan(args, config) -> int:
    items = scan(config, args.source)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "source_system": item.source_system,
                        "source_kind": item.source_kind,
                        "path": item.source_path.as_posix(),
                        "size": item.size,
                        "sha256": item.sha256,
                    }
                    for item in items
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    counts = Counter((item.source_system, item.source_kind) for item in items)
    print(f"Found {len(items)} memory files. No writes performed.")
    for (system, kind), count in sorted(counts.items()):
        print(f"  {system:<12} {kind:<22} {count}")
    return 0


def cmd_import(args, config) -> int:
    items = scan(config, args.source)
    sink = ArchiveFileSink(config, keep_versions=args.keep_versions)
    results = sink.import_items(items, incremental=args.incremental, limit=args.limit)
    counts = Counter(result.status for result in results)
    print(f"Scanned: {len(items)}")
    print(f"Imported/processed: {len(results)}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print(f"Archive root: {config.output_root}")
    return 0 if not counts.get("failed") else 1


def cmd_sync(args, config) -> int:
    summary, verification, _ = sync_archive(
        config,
        source=args.source,
        limit=args.limit,
        keep_versions=args.keep_versions,
        scan_secrets=not args.no_secret_scan,
    )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"Scanned: {summary['scanned']}")
        print(f"Selected: {summary['selected']}")
        print(f"Processed: {summary['processed']}")
        for key in ("added", "changed", "moved", "versioned", "skipped", "missing", "failed"):
            print(f"  {key}: {summary[key]}")
        print(f"Verification: {'OK' if verification.ok else 'FAILED'}")
        print(f"Archive root: {config.output_root}")
    return 0 if verification.ok and summary["failed"] == 0 else 1


def cmd_backup(args, config) -> int:
    summary, verification, report_path = sync_archive(
        config,
        source=args.source,
        limit=args.limit,
        keep_versions=True,
        scan_secrets=not args.no_secret_scan,
    )
    compile_result = None
    if not args.no_compile:
        compile_result = compile_archive(
            config,
            max_items_per_section=args.max_items,
            bootstrap_limit=args.bootstrap_limit,
        )
        verification = verify_archive(config, scan_secrets=not args.no_secret_scan)

    payload = {
        "sync": summary,
        "verification_ok": verification.ok,
        "archive_root": config.output_root.as_posix(),
        "report": report_path.as_posix(),
        "compiled": None
        if compile_result is None
        else {
            "output_dir": compile_result.output_dir.as_posix(),
            "item_count": compile_result.item_count,
            "files": [path.as_posix() for path in compile_result.files],
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("One-click memory backup complete.")
        print(f"Scanned: {summary['scanned']}")
        print(f"Processed: {summary['processed']}")
        for key in ("added", "changed", "moved", "versioned", "skipped", "missing", "failed"):
            print(f"  {key}: {summary[key]}")
        if compile_result is not None:
            print(f"Compiled records: {compile_result.item_count}")
            print(f"Memory Pack: {compile_result.output_dir}")
        print(f"Verification: {'OK' if verification.ok else 'FAILED'}")
        print(f"Archive root: {config.output_root}")
        print(f"Report: {report_path}")
    return 0 if verification.ok and summary["failed"] == 0 else 1


def sync_archive(
    config,
    *,
    source: str,
    limit: int | None,
    keep_versions: bool,
    scan_secrets: bool,
):
    items = scan(config, source)
    selected = items[:limit] if limit else items
    sink = ArchiveFileSink(config, keep_versions=keep_versions)
    manifest = sink.manifest

    states = {item.source_path.as_posix(): sync_state(manifest, sink, item) for item in selected}
    state_counts = Counter(states.values())
    to_import = [item for item in selected if states[item.source_path.as_posix()] != "skipped"]
    results = sink.import_items(to_import, incremental=True, write_report=False)

    source_systems = source_filter_to_systems(source)
    current_paths = {item.source_path.as_posix() for item in items}
    known_paths = manifest.latest_success_paths(source_systems)
    missing = [row for path, row in known_paths.items() if path not in current_paths]

    verification = verify_archive(config, scan_secrets=scan_secrets)
    result_counts = Counter(result.status for result in results)
    summary = {
        "scanned": len(items),
        "selected": len(selected),
        "processed": len(results),
        "added": state_counts.get("added", 0),
        "changed": state_counts.get("changed", 0),
        "moved": state_counts.get("moved", 0),
        "versioned": state_counts.get("versioned", 0),
        "skipped": state_counts.get("skipped", 0),
        "missing": len(missing),
        "failed": result_counts.get("failed", 0),
        "verification_ok": verification.ok,
    }
    report_path = sink.write_report(
        results,
        report_name="sync",
        extra={
            "sync": summary,
            "missing_sources": [
                {
                    "source_system": row["source_system"],
                    "source_kind": row["source_kind"],
                    "source_path": row["source_path"],
                    "archive_id": row["archive_id"],
                }
                for row in missing
            ],
            "verification_issues": [
                {"severity": issue.severity, "path": issue.path, "message": issue.message}
                for issue in verification.issues
            ],
        },
    )
    return summary, verification, report_path


def cmd_report(args, config) -> int:
    if args.latest:
        latest_path = config.unified_root / "reports" / "latest.json"
        if not latest_path.exists():
            print(f"No latest report found at {latest_path}")
            return 1
        print(latest_path.read_text(encoding="utf-8"))
        return 0

    manifest_path = config.manifest_path
    if not manifest_path.exists():
        print(f"No manifest found at {manifest_path}")
        return 1
    manifest = Manifest(manifest_path)
    print(f"Manifest: {manifest_path}")
    print("Counts:")
    for status, count in sorted(manifest.counts().items()):
        print(f"  {status}: {count}")
    print("Latest rows:")
    for row in manifest.latest_report_rows():
        print(f"  {row['archive_id']} {row['status']} {row['source_system']} {row['source_kind']}")
    return 0


def cmd_compile(args, config) -> int:
    result = compile_archive(
        config,
        max_items_per_section=args.max_items,
        bootstrap_limit=args.bootstrap_limit,
    )
    payload = {
        "output_dir": result.output_dir.as_posix(),
        "item_count": result.item_count,
        "files": [path.as_posix() for path in result.files],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Compiled records: {result.item_count}")
        print(f"Output: {result.output_dir}")
        for path in result.files:
            print(f"  {path.name}")
    return 0


def cmd_everos_import(args, config) -> int:
    result = import_memory_pack_to_everos(
        config,
        base_url=args.base_url,
        app_id=args.app_id,
        project_id=args.project_id,
        user_id=args.user_id,
        session_id=args.session_id,
        files=args.files,
        flush=not args.no_flush,
    )
    payload = {
        "base_url": result.base_url,
        "session_id": result.session_id,
        "app_id": result.app_id,
        "project_id": result.project_id,
        "user_id": result.user_id,
        "message_count": result.message_count,
        "add_status": result.add_status,
        "flush_status": result.flush_status,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("Imported Memory Pack into EverOS.")
        print(f"EverOS: {result.base_url}")
        print(f"Session: {result.session_id}")
        print(f"Scope: app_id={result.app_id} project_id={result.project_id}")
        print(f"User: {result.user_id}")
        print(f"Messages: {result.message_count}")
        print(f"Add status: {result.add_status}")
        if result.flush_status is not None:
            print(f"Flush status: {result.flush_status}")
    return 0


def cmd_show(args, config) -> int:
    manifest_path = config.manifest_path
    if not manifest_path.exists():
        print(f"No manifest found at {manifest_path}")
        return 1
    manifest = Manifest(manifest_path)
    row = manifest.get(args.id)
    if row is None:
        print(f"No record for archive id: {args.id}")
        return 1
    print(f"Archive id: {row['archive_id']}")
    print(f"Status: {row['status']}")
    print(f"Source: {row['source_path']}")
    print(f"Record: {row['record_path']}")
    print(f"Snapshot: {row['snapshot_path']}")
    return 0


def cmd_search(args, config) -> int:
    hits = search_archive(
        config,
        args.query,
        source=args.source,
        owner=args.owner,
        memory_type=args.memory_type,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps([hit.__dict__ for hit in hits], indent=2, ensure_ascii=False))
        return 0
    if not hits:
        print("No matches.")
        return 1
    for hit in hits:
        print(f"{hit.archive_id}  score={hit.score}")
        print(f"  {hit.title}")
        print(f"  {hit.source_system}/{hit.source_kind} owner={hit.owner_id} type={hit.memory_type}")
        print(f"  {hit.snippet}")
    return 0


def cmd_verify(args, config) -> int:
    result = verify_archive(config, scan_secrets=not args.no_secret_scan)
    print(f"Archive root: {config.output_root}")
    print(f"Checked rows: {result.checked_rows}")
    if result.ok:
        print("Verification: OK")
    else:
        print("Verification: FAILED")
    for issue in result.issues:
        print(f"  [{issue.severity}] {issue.path}: {issue.message}")
    return 0 if result.ok else 1


def cmd_stats(args, config) -> int:
    manifest_path = config.manifest_path
    if not manifest_path.exists():
        print(f"No manifest found at {manifest_path}")
        return 1
    manifest = Manifest(manifest_path)
    for field in ("status", "source_system", "source_kind", "owner_id", "memory_type"):
        print(f"{field}:")
        for key, count in sorted(manifest.grouped_counts(field).items()):
            print(f"  {key:<24} {count}")
    return 0


def cmd_init_config(args, config) -> int:
    path = args.path.expanduser()
    if path.exists() and not args.force:
        print(f"Refusing to overwrite existing config: {path}")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""[sources]
claude_code_root = "{config.claude_root}"
codex_memory_root = "{config.codex_memory_root}"
repo_roots = [{", ".join(f'"{root}"' for root in config.repo_roots)}]

[everos]
output_root = "{config.output_root}"
user_id = "{config.user_id}"

[everos.agents]
claude_code = "{config.claude_agent_id}"
codex = "{config.codex_agent_id}"
"""
    path.write_text(content, encoding="utf-8")
    print(f"Wrote config: {path}")
    return 0


def sync_state(manifest: Manifest, sink: ArchiveFileSink, item: SourceItem) -> str:
    if manifest.has_success(item.source_path, item.sha256):
        return "skipped" if sink.should_skip(item) else "versioned"
    if manifest.latest_success_for_path(item.source_path) is not None:
        return "changed"
    same_hash = manifest.latest_success_for_hash(item.sha256, item.source_system)
    if same_hash is not None and same_hash["source_path"] != item.source_path.as_posix():
        return "moved"
    return "added"


def source_filter_to_systems(value: str) -> set[str]:
    systems = parse_sources(value)
    result: set[str] = set()
    if "claude" in systems:
        result.add("claude_code")
    if "codex" in systems:
        result.add("codex")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
