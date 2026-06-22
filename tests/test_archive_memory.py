from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_memory.compiler import compile_archive
from archive_memory.config import ArchiveConfig, load_config
from archive_memory.redactor import find_secret_indicators, redact_text
from archive_memory.scanner import scan
from archive_memory.search import search_archive
from archive_memory.sinks.archive_files import ArchiveFileSink
from archive_memory.verify import verify_archive


class ArchiveMemoryTests(unittest.TestCase):
    def test_redacts_secret_assignments_and_keys(self) -> None:
        text = "api_key = sk-testsecretvalue123456789\npassword: hunter2\n"
        redacted = redact_text(text)
        self.assertIn("<redacted>", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertEqual(find_secret_indicators(redacted), [])

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


if __name__ == "__main__":
    unittest.main()
