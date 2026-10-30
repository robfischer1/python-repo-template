# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""The vendored opengrep taint rules: which sources reach the command sink.

Command injection is a confused-deputy bug, so sys.argv (set by whoever already
runs the process) is not a source for it, while HTTP request data and stdin are.
Runs the real rules over a tiny fixture with opengrep (or semgrep, same rule
language, via uvx when opengrep is not installed). Never skips.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

RULES = Path(__file__).resolve().parent.parent / "template" / "rules" / "sast" / "dataflow.yml"
CMD_RULE = "forge-taint-command-injection"
SEMGREP = "semgrep==1.183.0"

ARGV = "import subprocess\nimport sys\n\n\ndef run():\n    subprocess.run([sys.argv[1]])\n"
STDIN = "import subprocess\n\n\ndef run():\n    cmd = input()\n    subprocess.run([cmd])\n"
HTTP = (
    "import subprocess\n\n\n"
    "def run(request):\n    cmd = request.query_params\n    subprocess.run([cmd])\n"
)


async def _scan(argv: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    return out.decode()


def _hits(tmp_path: Path, body: str, name: str) -> set[str]:
    """Rule ids that fire on body. opengrep when on PATH, else semgrep via uvx."""
    src = tmp_path / f"{name}.py"
    src.write_text(body, encoding="utf-8")
    opengrep = shutil.which("opengrep")
    uvx = shutil.which("uvx")
    assert opengrep or uvx, "need opengrep or uvx to run the rules; this test never skips"
    base = (
        [opengrep, "scan"]
        if opengrep
        else [
            str(uvx),
            "--from",
            SEMGREP,
            "semgrep",
            "scan",
            "--metrics=off",
            "--disable-version-check",
        ]
    )
    argv = [
        *base,
        "--config",
        str(RULES),
        "--json",
        "--quiet",
        str(src),
    ]
    results = json.loads(asyncio.run(_scan(argv)))["results"]
    return {r["check_id"].rsplit(".", 1)[-1] for r in results}


def test_argv_to_subprocess_is_not_command_injection(tmp_path: Path) -> None:
    """An operator naming the binary they can already run is not an attack."""
    assert CMD_RULE not in _hits(tmp_path, ARGV, "argv")


@pytest.mark.parametrize(("name", "body"), [("stdin", STDIN), ("http", HTTP)])
def test_untrusted_input_to_subprocess_still_fires(tmp_path: Path, name: str, body: str) -> None:
    """Stdin and HTTP request data cross a trust boundary; they stay sources."""
    assert CMD_RULE in _hits(tmp_path, body, name)


def test_rules_file_is_ascii_only() -> None:
    """opengrep reads rule files under the C locale and chokes on non-ASCII."""
    RULES.read_text(encoding="ascii")
