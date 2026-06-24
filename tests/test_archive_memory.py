from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from archive_memory.cli import main as cli_main
from archive_memory.compiler import compile_archive
from archive_memory.config import ArchiveConfig, load_config
from archive_memory import everos_client
from archive_memory.everos_client import import_memory_pack_to_everos
from archive_memory.manifest import Manifest
from archive_memory.redactor import find_secret_indicators, redact_text
from archive_memory.scanner import scan
from archive_memory.search import search_archive
from archive_memory.sinks.archive_files import ArchiveFileSink
from archive_memory.verify import verify_archive

FAKE_OPENAI_KEY = "sk-" + "testsecretvalue123456789"
FAKE_GITHUB_TOKEN = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz123456"
FAKE_AWS_SECRET = "wJalrXUtnFEMI/" + "K7MDENG/bPxRfiCYzEXAMPLEKEY"
FAKE_BEARER_TOKEN = "Bearer " + "abcdefghijklmnopqrstuvwxyz123456"
FAKE_PASSWORD = "hunter" + "2"
FAKE_PRIVATE_KEY_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
FAKE_PRIVATE_KEY_END = "-----END " + "PRIVATE KEY-----"


class ArchiveMemoryTests(unittest.TestCase):
    def test_redacts_secret_assignments_and_keys(self) -> None:
        text = f"api_key = {FAKE_OPENAI_KEY}\npassword: {FAKE_PASSWORD}\n"
        redacted = redact_text(text)
        self.assertIn("<redacted>", redacted)
        self.assertNotIn(FAKE_PASSWORD, redacted)
        self.assertEqual(find_secret_indicators(redacted), [])

    def test_redacts_common_secret_formats_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex" / "memories"
            archive = root / "archive"
            codex.mkdir(parents=True)
            source = codex / "memory_summary.md"
            source.write_text(
                "\n".join(
                    [
                        f"api_key = {FAKE_OPENAI_KEY}",
                        f"GITHUB_TOKEN={FAKE_GITHUB_TOKEN}",
                        f"AWS_SECRET_ACCESS_KEY={FAKE_AWS_SECRET}",
                        f"Authorization: {FAKE_BEARER_TOKEN}",
                        '{"password": "' + FAKE_PASSWORD + '"}',
                        FAKE_PRIVATE_KEY_BEGIN,
                        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC",
                        FAKE_PRIVATE_KEY_END,
                    ]
                ),
                encoding="utf-8",
            )
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )

            sink = ArchiveFileSink(config)
            result = sink.import_items(scan(config, "codex"))[0]
            self.assertEqual(result.status, "imported", result.error)
            record = result.record_path.read_text(encoding="utf-8")
            snapshot = result.snapshot_path.read_text(encoding="utf-8")
            self.assertNotIn(FAKE_OPENAI_KEY, record)
            self.assertNotIn(FAKE_GITHUB_TOKEN, snapshot)
            self.assertNotIn(FAKE_PASSWORD, record)
            self.assertNotIn("PRIVATE KEY-----", snapshot)
            self.assertEqual(find_secret_indicators(record), [])
            row = Manifest(config.manifest_path).get(result.archive_id)
            self.assertIsNotNone(row)
            self.assertNotIn(FAKE_OPENAI_KEY, row["title"])
            self.assertTrue(verify_archive(config).ok)

    def test_config_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
[sources]
claude_code_root = "/tmp/claude"
codex_memory_root = "/tmp/codex"
repo_roots = ["/tmp/repo1", "/tmp/repo2"]

[everos]
output_root = "/tmp/archive"
user_id = "me"

[everos.agents]
claude_code = "cc"
codex = "cx"
""",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.user_id, "me")
            self.assertEqual(config.claude_agent_id, "cc")
            self.assertEqual(config.codex_agent_id, "cx")
            self.assertEqual(len(config.repo_roots), 2)

    def test_import_search_verify_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude = root / "claude"
            codex = root / "codex" / "memories"
            archive = root / "archive"
            (claude / "projects" / "-tmp-proj" / "memory").mkdir(parents=True)
            (codex / "rollout_summaries").mkdir(parents=True)

            (claude / "projects" / "-tmp-proj" / "memory" / "topic.md").write_text(
                "---\nname: Demo Topic\n---\nClaude memory about vector search.\n",
                encoding="utf-8",
            )
            (codex / "memory_summary.md").write_text("Codex prefers local code first.\n", encoding="utf-8")
            (codex / "rollout_summaries" / "run.md").write_text(
                "# Run\nInvestigated EverOS memory archive.\n",
                encoding="utf-8",
            )

            config = ArchiveConfig(
                claude_root=claude,
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )

            items = scan(config, "all")
            self.assertEqual(len(items), 3)
            sink = ArchiveFileSink(config)
            results = sink.import_items(items)
            self.assertEqual(len(results), 3)
            self.assertTrue(all(result.status == "imported" for result in results))
            self.assertEqual(sink.import_items(items), [])
            self.assertTrue((archive / "claude_code" / "sources").exists())
            self.assertTrue((archive / "claude_code" / "records").exists())
            self.assertTrue((archive / "codex" / "sources").exists())
            self.assertTrue((archive / "codex" / "records").exists())
            self.assertTrue((archive / "unified_index" / "manifest.sqlite").exists())

            hits = search_archive(config, "EverOS", limit=5)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].source_system, "codex")

            verification = verify_archive(config)
            self.assertTrue(verification.ok, verification.issues)
            self.assertEqual(verification.checked_rows, 3)

            protected = [p for p in archive.rglob("*") if ".claude" in p.parts or ".codex" in p.parts]
            self.assertEqual(protected, [])

    def test_keep_versions_writes_immutable_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex" / "memories"
            archive = root / "archive"
            codex.mkdir(parents=True)
            source = codex / "memory_summary.md"
            source.write_text("first version\n", encoding="utf-8")

            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )

            sink = ArchiveFileSink(config, keep_versions=True)
            first = sink.import_items(scan(config, "codex"))
            self.assertEqual(len(first), 1)
            first_snapshot = first[0].snapshot_path
            self.assertIn(".versions", first_snapshot.as_posix())
            self.assertTrue(first_snapshot.exists())
            self.assertTrue((archive / "codex" / "sources" / "memory_summary.md").exists())
            self.assertEqual(sink.import_items(scan(config, "codex")), [])

            source.write_text("second version\n", encoding="utf-8")
            second = sink.import_items(scan(config, "codex"))
            self.assertEqual(len(second), 1)
            second_snapshot = second[0].snapshot_path
            self.assertNotEqual(first_snapshot, second_snapshot)
            self.assertTrue(first_snapshot.exists())
            self.assertTrue(second_snapshot.exists())
            self.assertIn("second version", (archive / "codex" / "sources" / "memory_summary.md").read_text())

    def test_compile_generates_memory_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude = root / "claude"
            codex = root / "codex" / "memories"
            archive = root / "archive"
            (claude / "projects" / "-tmp-proj" / "memory").mkdir(parents=True)
            (codex / "skills" / "repo-research").mkdir(parents=True)
            (codex / "rollout_summaries").mkdir(parents=True)

            (claude / "projects" / "-tmp-proj" / "memory" / "prefs.md").write_text(
                "User prefers Chinese, direct, structured answers. Inspect local code first.\n",
                encoding="utf-8",
            )
            (codex / "skills" / "repo-research" / "SKILL.md").write_text(
                "---\nname: repo-research\n---\n# Workflow\nUse when comparing repository memory systems.\n",
                encoding="utf-8",
            )
            (codex / "memory_summary.md").write_text(
                "User prefers Chinese, direct, structured answers. Inspect local code first.\n",
                encoding="utf-8",
            )
            (codex / "rollout_summaries" / "project.md").write_text(
                f"cwd: {root / 'repos' / 'example-project'}\nBuild command is pytest.\n",
                encoding="utf-8",
            )

            config = ArchiveConfig(
                claude_root=claude,
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )
            sink = ArchiveFileSink(config)
            sink.import_items(scan(config, "all"))

            result = compile_archive(config)
            self.assertEqual(result.item_count, 4)
            expected = {
                "README.md",
                "memory_map.md",
                "recent_changes.md",
                "user_preferences.md",
                "agent_skills.md",
                "project_cases.md",
                "conflicts.md",
                "bootstrap_context.md",
            }
            self.assertEqual({path.name for path in result.files}, expected)
            self.assertTrue((archive / "compiled" / "bootstrap_context.md").exists())
            self.assertIn("Chinese", (archive / "compiled" / "user_preferences.md").read_text())
            self.assertIn("repo-research", (archive / "compiled" / "agent_skills.md").read_text())
            self.assertIn("example-project", (archive / "compiled" / "project_cases.md").read_text())
            self.assertIn("codex__", (archive / "compiled" / "memory_map.md").read_text())

    def test_scanner_rejects_source_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex" / "memories"
            outside = root / "outside-secret.md"
            (codex / "rollout_summaries").mkdir(parents=True)
            outside.write_text("UNIQUE_OUTSIDE_SECRET=plain-local-secret\n", encoding="utf-8")
            (codex / "rollout_summaries" / "linked.md").symlink_to(outside)
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=root / "archive",
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )
            self.assertEqual(scan(config, "codex"), [])

    def test_archive_rejects_output_symlink_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex" / "memories"
            archive = root / "archive"
            outside = root / "outside-overwrite.txt"
            codex.mkdir(parents=True)
            outside.write_text("keep me\n", encoding="utf-8")
            source = codex / "memory_summary.md"
            source.write_text("safe memory\n", encoding="utf-8")
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )
            sink = ArchiveFileSink(config)
            item = scan(config, "codex")[0]
            target = sink.latest_snapshot_path(item)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(outside)

            result = sink.import_item(item)
            self.assertEqual(result.status, "failed")
            self.assertEqual(outside.read_text(encoding="utf-8"), "keep me\n")

    def test_search_and_compile_reject_manifest_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex" / "memories"
            archive = root / "archive"
            outside = root / "outside-record.md"
            codex.mkdir(parents=True)
            outside.write_text("PROJECT_SECRET_TOKEN=topsecret-local-value\n", encoding="utf-8")
            (codex / "memory_summary.md").write_text("normal memory\n", encoding="utf-8")
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=codex,
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )
            sink = ArchiveFileSink(config)
            result = sink.import_items(scan(config, "codex"))[0]
            with sqlite3.connect(config.manifest_path) as conn:
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
                        "evil",
                        "codex",
                        "summary",
                        str(codex / "evil.md"),
                        "hash",
                        0.0,
                        1,
                        "user",
                        "tester",
                        "reference",
                        "",
                        "evil",
                        result.snapshot_path.as_posix(),
                        outside.as_posix(),
                        "2026-01-01T00:00:00+00:00",
                        "imported",
                        None,
                    ),
                )
            with self.assertRaises(RuntimeError):
                search_archive(config, "PROJECT_SECRET_TOKEN")
            with self.assertRaises(RuntimeError):
                compile_archive(config)

    def test_backup_command_runs_one_click_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex" / "memories"
            archive = root / "archive"
            config_path = root / "config.toml"
            codex.mkdir(parents=True)
            (codex / "memory_summary.md").write_text("User prefers local code first.\n", encoding="utf-8")
            config_path.write_text(
                f"""
[sources]
claude_code_root = "{root / 'claude'}"
codex_memory_root = "{codex}"
repo_roots = ["{root / 'repos'}"]

[everos]
output_root = "{archive}"
user_id = "tester"

[everos.agents]
claude_code = "claude-code"
codex = "codex"
""",
                encoding="utf-8",
            )
            code = cli_main(["--config", str(config_path), "backup", "--source", "codex"])
            self.assertEqual(code, 0)
            self.assertTrue((archive / "compiled" / "bootstrap_context.md").exists())
            self.assertTrue(verify_archive(load_config(config_path)).ok)

    def test_backup_to_everos_script_accepts_relative_config_from_any_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = root / "runner"
            codex = root / "codex" / "memories"
            archive = root / "archive"
            runner.mkdir()
            codex.mkdir(parents=True)
            (codex / "memory_summary.md").write_text("User prefers local script tests.\n", encoding="utf-8")
            (runner / "local.toml").write_text(
                f"""
[sources]
claude_code_root = "{root / 'claude'}"
codex_memory_root = "{codex}"
repo_roots = ["{root / 'repos'}"]

[everos]
output_root = "{archive}"
user_id = "tester"

[everos.agents]
claude_code = "claude-code"
codex = "codex"
""",
                encoding="utf-8",
            )
            (runner / "everos-local.env").write_text(
                "\n".join(
                    [
                        "EVEROS_LLM__BASE_URL=http://127.0.0.1:11434/v1",
                        "EVEROS_MULTIMODAL__BASE_URL=http://127.0.0.1:11434/v1",
                        "EVEROS_EMBEDDING__BASE_URL=http://127.0.0.1:8001/v1",
                        "EVEROS_RERANK__BASE_URL=http://127.0.0.1:8002/v1",
                    ]
                ),
                encoding="utf-8",
            )

            requests: list[tuple[str, dict]] = []

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    requests.append((self.path, payload))
                    status = "accumulated" if self.path.endswith("/add") else "extracted"
                    body = json.dumps({"request_id": "test", "data": {"status": status}}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, format: str, *args) -> None:  # noqa: A002
                    return

            server = HTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                repo_root = Path(__file__).resolve().parents[1]
                script = repo_root / "scripts" / "backup-to-everos.sh"
                completed = subprocess.run(
                    [
                        str(script),
                        "--config=local.toml",
                        "--base-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--everos-env-file=everos-local.env",
                        "--user-id",
                        "tester",
                    ],
                    cwd=runner,
                    env={**os.environ, "PYTHON": sys.executable},
                    text=True,
                    capture_output=True,
                    check=False,
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue((archive / "compiled" / "bootstrap_context.md").exists())
            self.assertEqual([path for path, _ in requests], ["/api/v1/memory/add", "/api/v1/memory/flush"])
            self.assertEqual(requests[0][1]["messages"][0]["sender_id"], "tester")

    def test_everos_import_posts_memory_pack_and_flushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            compiled = archive / "compiled"
            compiled.mkdir(parents=True)
            (compiled / "bootstrap_context.md").write_text("# Bootstrap\nUser prefers local code first.\n", encoding="utf-8")
            (compiled / "user_preferences.md").write_text("# Preferences\nUse Chinese answers.\n", encoding="utf-8")
            env_file = root / "everos-local.env"
            env_file.write_text(
                "\n".join(
                    [
                        "EVEROS_LLM__BASE_URL=http://127.0.0.1:11434/v1",
                        "EVEROS_MULTIMODAL__BASE_URL=http://127.0.0.1:11434/v1",
                        "EVEROS_EMBEDDING__BASE_URL=http://127.0.0.1:8001/v1",
                        "EVEROS_RERANK__BASE_URL=http://127.0.0.1:8002/v1",
                    ]
                ),
                encoding="utf-8",
            )
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=root / "codex" / "memories",
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )
            calls: list[tuple[str, str, dict]] = []
            original = everos_client.post_json

            def fake_post_json(base_url: str, path: str, payload: dict) -> dict:
                calls.append((base_url, path, payload))
                status = "accumulated" if path.endswith("/add") else "extracted"
                return {"request_id": "test", "data": {"status": status}}

            try:
                everos_client.post_json = fake_post_json
                result = import_memory_pack_to_everos(
                    config,
                    base_url="http://127.0.0.1:8000",
                    app_id="agent-memory-archive",
                    project_id="codex-claude-code",
                    user_id="tester",
                    session_id="session-1",
                    everos_env_file=env_file,
                )
            finally:
                everos_client.post_json = original

            self.assertEqual(result.message_count, 2)
            self.assertEqual(result.add_status, "accumulated")
            self.assertEqual(result.flush_status, "extracted")
            self.assertEqual([call[1] for call in calls], ["/api/v1/memory/add", "/api/v1/memory/flush"])
            add_payload = calls[0][2]
            self.assertEqual(add_payload["session_id"], "session-1")
            self.assertEqual(add_payload["messages"][0]["sender_id"], "tester")
            self.assertIn("Imported Memory Pack File", add_payload["messages"][0]["content"])

    def test_everos_import_rejects_remote_api_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            (archive / "compiled").mkdir(parents=True)
            (archive / "compiled" / "bootstrap_context.md").write_text("# Bootstrap\n", encoding="utf-8")
            env_file = root / "everos-local.env"
            env_file.write_text("EVEROS_LLM__BASE_URL=http://127.0.0.1:11434/v1\n", encoding="utf-8")
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=root / "codex" / "memories",
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )

            with self.assertRaisesRegex(RuntimeError, "non-local host"):
                import_memory_pack_to_everos(
                    config,
                    base_url="https://everos.example.com",
                    everos_env_file=env_file,
                )

    def test_everos_import_rejects_remote_model_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            (archive / "compiled").mkdir(parents=True)
            (archive / "compiled" / "bootstrap_context.md").write_text("# Bootstrap\n", encoding="utf-8")
            env_file = root / "everos-remote.env"
            env_file.write_text(
                "\n".join(
                    [
                        "EVEROS_LLM__BASE_URL=https://openrouter.ai/api/v1",
                        "EVEROS_MULTIMODAL__BASE_URL=http://127.0.0.1:11434/v1",
                        "EVEROS_EMBEDDING__BASE_URL=http://127.0.0.1:8001/v1",
                        "EVEROS_RERANK__BASE_URL=http://127.0.0.1:8002/v1",
                    ]
                ),
                encoding="utf-8",
            )
            config = ArchiveConfig(
                claude_root=root / "claude",
                codex_memory_root=root / "codex" / "memories",
                repo_roots=(root / "repos",),
                output_root=archive,
                user_id="tester",
                claude_agent_id="claude-code",
                codex_agent_id="codex",
            )

            with self.assertRaisesRegex(RuntimeError, "non-local host"):
                import_memory_pack_to_everos(
                    config,
                    base_url="http://127.0.0.1:8000",
                    everos_env_file=env_file,
                )


if __name__ == "__main__":
    unittest.main()
