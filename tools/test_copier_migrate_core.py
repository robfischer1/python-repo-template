# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vendored copier_migrate tool that every template repo shares.

THIS FILE IS BYTE-IDENTICAL in python-, go-, rust- and frontend-repo-template,
like tools/copier_migrate.py beside it. A template cannot import across repos,
so the tool is vendored, and TOOL_SHA256 below is the drift alarm: change the
tool in one repo and this test fails until the pin moves, which makes the edit
a visible diff in this file; the other three repos then differ from this one.
To change the tool, change all four copies and this pin together.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import copier_migrate as cm
import pytest

TOOL = Path(cm.__file__).resolve()
TOOL_SHA256 = "f8453d4091673f7280bc803b51d4056dddd59b9f20cc2c20c210435ade9959ce"


def test_vendored_tool_is_the_pinned_copy() -> None:
    """Fails when this repo's copy drifts from the one the four templates share."""
    assert hashlib.sha256(TOOL.read_bytes()).hexdigest() == TOOL_SHA256


# --- recipes: the gates and options the go / rust / frontend sweeps need ----------

JUST = "set shell := [\"bash\"]\n\nimport 'stages.just'\n\ndefault:\n    @just --list\n\n"
PAIR = {"name": "a", "old": ["# c\na:\n    old"], "new": ["[doc('x')]\na:\n    new"]}


def write(tmp: Path, text: str, *, dev: bool = False) -> Path:
    j = tmp / "justfile"
    j.write_text(text, encoding="utf-8")
    if dev:
        (tmp / "dev.just").write_text("_dev VERB:\n    true\n", encoding="utf-8")
    return j


def test_need_re_gates_a_justfile_that_lacks_the_dev_import(tmp_path: Path) -> None:
    j = write(tmp_path, JUST + "# c\na:\n    old\n")
    spec = {"need_re": r"^import\??\s+'dev\.just'", "pairs": [PAIR]}
    assert cm.recipes(j, spec) == "gated"
    assert "old" in j.read_text(encoding="utf-8")


def test_need_re_lets_a_justfile_with_the_import_through(tmp_path: Path) -> None:
    j = write(tmp_path, "import? 'dev.just'\n\n# c\na:\n    old\n")
    spec = {"need_re": r"^import\??\s+'dev\.just'", "pairs": [PAIR]}
    assert cm.recipes(j, spec) == "swept"
    assert j.read_text(encoding="utf-8") == "import? 'dev.just'\n\n[doc('x')]\na:\n    new\n"


def test_done_new_picks_which_replacement_marks_a_recipe_done(tmp_path: Path) -> None:
    """With done_new=1 only the second `new` (the comment-less form) counts as done."""
    pair = {
        "name": "a",
        "old": ["a:\n    old"],
        "new": ["# long\n[doc('l')]\na:\n    new", "[doc('s')]\na:\n    new"],
    }
    j = write(tmp_path, "[doc('s')]\na:\n    new\n\na:\n    old\n")
    assert cm.recipes(j, {"pairs": [pair], "done_new": 1}) == "kept"  # skipped: already done
    j = write(tmp_path, "# long\n[doc('l')]\na:\n    new\n\na:\n    old\n")
    assert cm.recipes(j, {"pairs": [pair], "done_new": 1}) == "swept"  # new[1] absent: sweeps
    assert cm.recipes(j, {"pairs": [pair]}) == "kept"  # any(): new[0] present: skipped


def test_keep_attrs_leaves_the_doc_line_above_the_old_recipe(tmp_path: Path) -> None:
    pair = {"name": "a", "old": ["a:\n    old"], "new": ["a:\n    new"]}
    text = "[doc('mine')]\na:\n    old\n"
    j = write(tmp_path, text)
    assert cm.recipes(j, {"pairs": [pair]}) == "swept"
    assert j.read_text(encoding="utf-8") == "a:\n    new\n"
    j = write(tmp_path, text)
    assert cm.recipes(j, {"pairs": [pair], "keep_attrs": True}) == "swept"
    assert j.read_text(encoding="utf-8") == "[doc('mine')]\na:\n    new\n"


def test_lines_rewrite_everywhere_and_honour_unless(tmp_path: Path) -> None:
    pair = {"name": "a", "old": ["a:\n    old"], "new": ["a:\n    new"]}
    lines = [
        {"old": "    clean\n", "new": ""},
        {"old": "_dirs := x\n", "new": "", "unless": r"\{\{\s*_dirs\s*\}\}"},
    ]
    j = write(tmp_path, "_dirs := x\nb:\n    clean\nc:\n    clean\n\na:\n    old\n")
    assert cm.recipes(j, {"pairs": [pair], "lines": lines}) == "swept"
    assert j.read_text(encoding="utf-8") == "b:\nc:\n\na:\n    new\n"
    j = write(tmp_path, "_dirs := x\nd:\n    {{ _dirs }}\n\na:\n    old\n")
    assert cm.recipes(j, {"pairs": [pair], "lines": lines}) == "swept"
    assert "_dirs := x\n" in j.read_text(encoding="utf-8")  # a kept recipe still reads it
    j = write(tmp_path, "_dirs := x\nd:\n    echo\n\na:\n    old\n")
    assert cm.recipes(j, {"pairs": [pair], "lines": lines}) == "swept"
    assert "_dirs" not in j.read_text(encoding="utf-8")


def test_lines_do_not_run_when_no_recipe_swept(tmp_path: Path) -> None:
    pair = {"name": "a", "old": ["a:\n    old"], "new": ["a:\n    new"]}
    j = write(tmp_path, "    clean\na:\n    mine\n")
    assert cm.recipes(j, {"pairs": [pair], "lines": [{"old": "    clean\n", "new": ""}]}) == "kept"
    assert "clean" in j.read_text(encoding="utf-8")


def test_retire_epilogue_prints_on_every_outcome(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = {"sha256": ["0" * 64], "epilogue": "drop the dead key"}
    assert cm.retire(tmp_path / "nope", spec) == "absent"
    assert "drop the dead key" in capsys.readouterr().out
    f = tmp_path / "x"
    f.write_text("mine\n", encoding="utf-8")
    assert cm.retire(f, spec) == "kept"
    assert "drop the dead key" in capsys.readouterr().out


# --- referee: the star's own package.json keys survive an update ------------------


def prev_pkg(tmp: Path, data: dict[str, Any]) -> Path:
    p = tmp / ".copier-prev" / "package.json"
    p.parent.mkdir()
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_referee_restores_the_stars_keys_in_the_stars_order(tmp_path: Path) -> None:
    prev = prev_pkg(
        tmp_path,
        {"name": "s", "version": "1.2.3", "scripts": {"a": "1"}, "devDependencies": {"x": "^2"}},
    )
    pkg = tmp_path / "package.json"
    pkg.write_text(
        json.dumps({"scripts": {"a": "2"}, "name": "s", "version": "0.1.0", "extra": 1}),
        encoding="utf-8",
    )
    assert cm.referee(pkg, prev) == "restored"
    out = json.loads(pkg.read_text(encoding="utf-8"))
    assert out["version"] == "1.2.3"
    assert out["devDependencies"] == {"x": "^2"}
    assert out["scripts"] == {"a": "2"}  # the template's key stays the template's
    assert list(out) == ["name", "version", "scripts", "devDependencies", "extra"]
    assert pkg.read_text(encoding="utf-8").endswith("}\n")


def test_referee_with_nothing_to_restore_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = {"name": "s", "version": "1"}
    prev = prev_pkg(tmp_path, data)
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps(data), encoding="utf-8")
    assert cm.referee(pkg, prev) == "clean"
    assert "needed no refereeing" in capsys.readouterr().out


def test_referee_leaves_an_unparsable_package_json_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prev = prev_pkg(tmp_path, {"version": "1"})
    pkg = tmp_path / "package.json"
    pkg.write_text("<<<<<<< conflict\n", encoding="utf-8")
    assert cm.referee(pkg, prev) == "kept"
    assert pkg.read_text(encoding="utf-8") == "<<<<<<< conflict\n"
    assert "leaving it ALONE" in capsys.readouterr().out


def test_referee_without_a_previous_copy_is_a_noop(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text('{"version":"1"}', encoding="utf-8")
    assert cm.referee(pkg, tmp_path / ".copier-prev" / "package.json") == "absent"
    assert pkg.read_text(encoding="utf-8") == '{"version":"1"}'


def test_referee_removes_the_previous_copy_it_was_handed(tmp_path: Path) -> None:
    prev = prev_pkg(tmp_path, {"version": "1"})
    pkg = tmp_path / "package.json"
    pkg.write_text('{"version": "1"}', encoding="utf-8")
    cm.referee(pkg, prev)
    assert not prev.exists()
    assert not prev.parent.exists()


def test_main_runs_referee(tmp_path: Path) -> None:
    prev = prev_pkg(tmp_path, {"version": "9"})
    pkg = tmp_path / "package.json"
    pkg.write_text('{"version": "1"}', encoding="utf-8")
    assert cm.main(["referee", str(pkg), "--prev", str(prev)]) == 0
    assert json.loads(pkg.read_text(encoding="utf-8"))["version"] == "9"
