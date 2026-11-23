# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""template/.gitignore must be OPEN + gitignore.rules + CLOSE, byte for byte."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "python-repo-template"
OPEN = f"# >>> {NAME} — managed block, edits here are overwritten >>>"
CLOSE = f"# <<< {NAME} <<<"


def test_wrapped_gitignore_matches_rules() -> None:
    rules = (ROOT / "gitignore.rules").read_text(encoding="utf-8").rstrip("\n")
    want = f"{OPEN}\n{rules}\n{CLOSE}\n"
    have = (ROOT / "template" / ".gitignore").read_text(encoding="utf-8")
    assert have == want, "template/.gitignore drifted from gitignore.rules"
