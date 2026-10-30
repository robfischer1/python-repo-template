# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""A fresh render must pass the ruff gate it ships with.

The gate's ``template:render-matrix`` atom only checks present / absent / parse,
so nothing graded the *formatting* of the rendered Python. v0.44.0 moved
``line-length`` from 88 to 100 and left two jinja sources wrapped at 88: every
new star was born failing ``ruff format --check``. This test renders the
cases that carry Python and runs the render's own ruff config over them.

copier and uvx are hard requirements: a missing tool FAILS, it never skips.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = ("star", "star-no-mcp", "library")
COPIER = "copier==9.19.1"


def _case(name: str) -> dict[str, object]:
    matrix = tomllib.loads((ROOT / "ci-matrix.toml").read_text(encoding="utf-8"))
    return next(c for c in matrix["case"] if c["name"] == name)


def _ruff_pin(dest: Path) -> str:
    text = (dest / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'"ruff==([0-9.]+)"', text)
    assert found, "rendered pyproject.toml pins no ruff"
    return f"ruff=={found.group(1)}"


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # tool-conflict: S603 flags every subprocess call, and this one runs argv built here from a pinned copier version and the matrix file
        argv, cwd=cwd, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("name", CASES)
def test_render_passes_ruff(name: str, tmp_path: Path) -> None:
    """Render the case, then run the render's pinned ruff format + check over it."""
    uvx = shutil.which("uvx")
    assert uvx, "uvx is required to render the template; this test never skips"
    answers = _case(name)["answers"]
    assert isinstance(answers, dict)
    dest = tmp_path / "render"
    argv = [
        uvx,
        "--from",
        COPIER,
        "copier",
        "copy",
        "--trust",
        "--skip-tasks",
        "--vcs-ref=HEAD",
        "--defaults",
        "--quiet",
    ]
    for key, value in answers.items():
        argv += ["--data", f"{key}={str(value).lower() if isinstance(value, bool) else value}"]
    argv += [str(ROOT), str(dest)]
    rendered = _run(argv, tmp_path)
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr

    pin = _ruff_pin(dest)
    for sub in (["format", "--check"], ["check"]):
        result = _run([uvx, pin, *sub], dest)
        assert result.returncode == 0, (
            f"{name}: ruff {' '.join(sub)}\n{result.stdout}{result.stderr}"
        )
