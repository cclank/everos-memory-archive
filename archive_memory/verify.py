from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archive_memory.config import ArchiveConfig
from archive_memory.manifest import Manifest
from archive_memory.redactor import find_secret_indicators
from archive_memory.utils import is_relative_to, read_text_lossy


@dataclass(frozen=True)
class VerificationIssue:
    severity: str
    path: str
    message: str


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    checked_rows: int
    issues: list[VerificationIssue]


def verify_archive(config: ArchiveConfig, *, scan_secrets: bool = True) -> VerificationResult:
    issues: list[VerificationIssue] = []
    root = config.output_root.resolve()
    manifest_path = config.manifest_path.resolve()

    if any(is_relative_to(root, protected) for protected in config.protected_roots):
        issues.append(VerificationIssue("error", root.as_posix(), "archive root is inside a protected source root"))
    if config.manifest_path.is_symlink():
        issues.append(VerificationIssue("error", config.manifest_path.as_posix(), "manifest path is a symlink"))

    if not manifest_path.exists():
        issues.append(VerificationIssue("error", manifest_path.as_posix(), "manifest does not exist"))
        return VerificationResult(False, 0, issues)

    manifest = Manifest(manifest_path, create=False)
    rows = manifest.iter_rows()
    for row in rows:
        for field in ("record_path", "snapshot_path"):
            raw_path = Path(row[field])
            if raw_path.is_symlink():
                issues.append(VerificationIssue("error", raw_path.as_posix(), f"{field} is a symlink"))
            path = raw_path.resolve()
            if not raw_path.exists():
                issues.append(VerificationIssue("error", raw_path.as_posix(), f"{field} is missing"))
                continue
            if not is_relative_to(path, root):
                issues.append(VerificationIssue("error", path.as_posix(), f"{field} is outside archive root"))
            expected_source_root = config.source_archive_root(row["source_system"]).resolve()
            if not is_relative_to(path, expected_source_root):
                issues.append(
                    VerificationIssue(
                        "error",
                        path.as_posix(),
                        f"{field} is not under source-specific archive root {expected_source_root}",
                    )
                )
            if any(is_relative_to(path, protected) for protected in config.protected_roots):
                issues.append(VerificationIssue("error", path.as_posix(), f"{field} is inside protected source root"))
            if scan_secrets:
                indicators = find_secret_indicators(read_text_lossy(path))
                if indicators:
                    issues.append(
                        VerificationIssue(
                            "error",
                            path.as_posix(),
                            f"unredacted secret indicators remain: {', '.join(indicators)}",
                        )
                    )

        source_path = Path(row["source_path"])
        if not source_path.exists():
            issues.append(VerificationIssue("warning", source_path.as_posix(), "source file no longer exists"))

    ok = not any(issue.severity == "error" for issue in issues)
    return VerificationResult(ok, len(rows), issues)
