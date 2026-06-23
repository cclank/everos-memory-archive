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
    r"(?i)((?:^|[^\w])[\"']?"
    r"(?:aws[_-]?secret[_-]?access[_-]?key|github[_-]?token|bearer[_-]?token|"
    r"api[_-]?key|secret|token|password|credential|client[_-]?secret|private[_-]?key|"
    r"auth[_-]?token|anthropic[_-]?auth[_-]?token)"
    r"[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,;}]+)"
    r"([\"']?)",
    re.MULTILINE,
)

OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")
ANTHROPIC_KEY_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b")
GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b")
AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b")
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def is_sensitive_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SENSITIVE_PATH_PARTS)


def redact_text(text: str) -> str:
    text = PRIVATE_KEY_RE.sub("<redacted-private-key>", text)
    text = BEARER_TOKEN_RE.sub("Bearer <redacted>", text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}<redacted>{m.group(3)}", text)
    text = OPENAI_KEY_RE.sub("sk-<redacted>", text)
    text = ANTHROPIC_KEY_RE.sub("sk-ant-<redacted>", text)
    text = GITHUB_TOKEN_RE.sub("github-<redacted>", text)
    text = AWS_ACCESS_KEY_RE.sub("aws-<redacted>", text)
    return text


def find_secret_indicators(text: str) -> list[str]:
    hits: list[str] = []
    if OPENAI_KEY_RE.search(text):
        hits.append("openai_key")
    if ANTHROPIC_KEY_RE.search(text):
        hits.append("anthropic_key")
    if GITHUB_TOKEN_RE.search(text):
        hits.append("github_token")
    if AWS_ACCESS_KEY_RE.search(text):
        hits.append("aws_access_key")
    if BEARER_TOKEN_RE.search(text):
        hits.append("bearer_token")
    if PRIVATE_KEY_RE.search(text):
        hits.append("private_key")
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        if match.group(2) != "<redacted>":
            hits.append("secret_assignment")
            break
    return hits
