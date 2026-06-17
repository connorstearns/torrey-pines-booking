from __future__ import annotations

from pathlib import Path


def test_env_file_is_gitignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert ".env" in gitignore.splitlines()


def test_no_obvious_secret_patterns_are_committed() -> None:
    patterns = [
        "hooks.slack.com/" + "services",
        "PHP" + "SESSID=",
        "x-" + "authorization",
        "Bearer " + "eyJ",
        "__" + "stripe",
        "_dd" + "_s=",
    ]
    excluded_parts = {".git", "__pycache__", ".pytest_cache", ".test-data"}
    offenders: list[str] = []

    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if pattern in text:
                offenders.append(str(path))

    assert offenders == []
