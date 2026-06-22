from __future__ import annotations

import re
from pathlib import Path


SENSITIVE_PATH_PARTS = {
    ".credentials.json",
    ".env",
    "cache",
    "daemon",
    "downloads",
    "file-history",
    "jobs",
    "paste-cache",
    "session-env",
    "sessions",
    "shell-snapshots",
    "tasks",
    "telemetry",
    ".git",
}

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|credential|auth[_-]?token|anthropic[_-]?auth[_-]?token)"
    r"(\s*[:=]\s*)"
    r"([\"']?)([^\"'\s,;]+)"
)

OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")
ANTHROPIC_KEY_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b")


def is_sensitive_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SENSITIVE_PATH_PARTS)


def redact_text(text: str) -> str:
    text = SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}<redacted>", text)
    text = OPENAI_KEY_RE.sub("sk-<redacted>", text)
    text = ANTHROPIC_KEY_RE.sub("sk-ant-<redacted>", text)
    return text


def find_secret_indicators(text: str) -> list[str]:
    hits: list[str] = []
    if OPENAI_KEY_RE.search(text):
        hits.append("openai_key")
    if ANTHROPIC_KEY_RE.search(text):
        hits.append("anthropic_key")
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        if match.group(4) != "<redacted>":
            hits.append("secret_assignment")
            break
    return hits
