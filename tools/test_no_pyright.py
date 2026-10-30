# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""The template ships no pyright: the fleet dropped it, mypy is the one checker.

foundry-tools grades python with mypy and has no pyright atom, so a pyright
dependency, [tool.pyright] table, recipe or checklist line in a render is dead
weight that disagrees with the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORD = re.compile(r"\bpyright\b", re.IGNORECASE)


def test_template_tree_never_mentions_pyright() -> None:
    """No file under template/ names pyright, in content or in its path."""
    hits = [
        str(p.relative_to(ROOT))
        for p in sorted((ROOT / "template").rglob("*"))
        if WORD.search(str(p.relative_to(ROOT)))
        or (p.is_file() and WORD.search(p.read_text(encoding="utf-8", errors="ignore")))
    ]
    assert not hits, hits


def test_mypy_stays_strict_in_the_rendered_pyproject() -> None:
    """Dropping the second checker must not loosen the one that remains."""
    text = (ROOT / "template" / "pyproject.toml.jinja").read_text(encoding="utf-8")
    assert "[tool.mypy]" in text
    assert re.search(r"^strict\s*=\s*true", text, re.MULTILINE)
