from __future__ import annotations

import subprocess
from pathlib import Path

SECRET_PATTERNS = [
    "hooks.slack.com/" + "services",
    "PHP" + "SESSID=",
    "x-" + "authorization",
    "Bearer " + "eyJ",
    "__" + "stripe",
    "_dd" + "_s=",
]

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".test-data",
    "logs",
}


def test_env_file_is_gitignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert ".env" in gitignore.splitlines()


def _is_excluded(path: Path) -> bool:
    if path.name == ".env" or path.name.endswith(".env"):
        return True
    if path.suffix == ".db":
        return True
    return any(part in EXCLUDED_PARTS for part in path.parts)


def _tracked_or_project_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [
            path
            for path in Path(".").rglob("*")
            if path.is_file() and not _is_excluded(path)
        ]

    return [
        Path(line)
        for line in result.stdout.splitlines()
        if line.strip() and not _is_excluded(Path(line))
    ]


def _secret_scan_offenders() -> list[str]:
    offenders: list[str] = []
    for path in _tracked_or_project_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern in text:
                offenders.append(str(path))
                break
    return offenders


def test_no_obvious_secret_patterns_are_committed() -> None:
    assert _secret_scan_offenders() == []


def test_local_env_file_is_ignored_by_secret_scan() -> None:
    env_path = Path(".env")
    original = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    try:
        env_path.write_text(
            "SLACK_WEBHOOK_URL=https://" + SECRET_PATTERNS[0] + "/local-only\n",
            encoding="utf-8",
        )

        assert _secret_scan_offenders() == []
    finally:
        if original is None:
            env_path.unlink(missing_ok=True)
        else:
            env_path.write_text(original, encoding="utf-8")
