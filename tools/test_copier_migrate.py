# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for tools/copier_migrate.py and the copier.yml entries that call it."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import copier_migrate as cm
import pytest

ROOT = Path(__file__).resolve().parent.parent
MIG = ROOT / "migrations"
NAME = "python-repo-template"


def spec(name: str) -> dict[str, Any]:
    return json.loads((MIG / name).read_text(encoding="utf-8"))


def write_spec(tmp: Path, data: dict[str, object]) -> Path:
    p = tmp / "spec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# --- retire -----------------------------------------------------------------


def test_retire_deletes_a_shipped_rendering(tmp_path: Path) -> None:
    f = tmp_path / ".pre-commit-config.yaml"
    f.write_bytes(b"repos: []\n")
    s = {"sha256": [hashlib.sha256(b"repos: []\n").hexdigest()]}
    assert cm.retire(f, s) == "deleted"
    assert not f.exists()


def test_retire_leaves_an_edited_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / ".pre-commit-config.yaml"
    f.write_text("edited\n", encoding="utf-8")
    assert cm.retire(f, {"sha256": ["0" * 64]}) == "kept"
    assert f.exists()
    assert "LEAVING IT ALONE" in capsys.readouterr().out


def test_retire_absent_is_a_noop(tmp_path: Path) -> None:
    assert cm.retire(tmp_path / "nope", {"sha256": []}) == "absent"


def test_shipped_pre_commit_spec_carries_all_83_renderings() -> None:
    hashes = cm.strs(spec("v0.34.0-pre-commit.json"), "sha256")
    assert len(set(hashes)) == 83
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)


# --- swap -------------------------------------------------------------------

SWAP = {"label": "lint recipe", "old": ["OLD-A\n", "OLD-B\n"], "new": "NEW\n", "version": "v9"}


def test_swap_replaces_a_prior_shape(tmp_path: Path) -> None:
    f = tmp_path / "justfile"
    f.write_text("x\nOLD-B\ny\n", encoding="utf-8")
    assert cm.swap(f, SWAP) == "swept"
    assert f.read_text(encoding="utf-8") == "x\nNEW\ny\n"


def test_swap_is_idempotent(tmp_path: Path) -> None:
    f = tmp_path / "justfile"
    f.write_text("NEW\n", encoding="utf-8")
    assert cm.swap(f, SWAP) == "current"


def test_swap_leaves_an_unknown_shape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "justfile"
    f.write_text("mine\n", encoding="utf-8")
    assert cm.swap(f, SWAP) == "kept"
    assert f.read_text(encoding="utf-8") == "mine\n"
    assert "against v9" in capsys.readouterr().out


def test_swap_absent(tmp_path: Path) -> None:
    assert cm.swap(tmp_path / "justfile", SWAP) == "absent"


@pytest.mark.parametrize(
    "name", ["v0.20.2-release.json", "v0.25.13-lint.json", "v0.34.0-lint.json"]
)
def test_shipped_swap_specs_round_trip(tmp_path: Path, name: str) -> None:
    s = spec(name)
    for old in cm.strs(s, "old"):
        f = tmp_path / "justfile"
        f.write_text("head\n" + old + "tail\n", encoding="utf-8")
        assert cm.swap(f, s) == "swept"
        assert cm.strs(s, "new")[0] in f.read_text(encoding="utf-8")


def test_v0_34_lint_chain_follows_v0_25() -> None:
    """A star at the original recipe crossing both versions lands on v0.34.0's."""
    assert cm.strs(spec("v0.25.13-lint.json"), "new")[0] in cm.strs(
        spec("v0.34.0-lint.json"), "old"
    )


# --- managed-block ------------------------------------------------------------


def test_managed_block_appends_and_is_idempotent(tmp_path: Path) -> None:
    g, rules = tmp_path / ".gitignore", tmp_path / "rules"
    g.write_text("*.log\n", encoding="utf-8")
    rules.write_text("a\nb\n", encoding="utf-8")
    assert cm.managed_block(g, rules, NAME, ["hint"]) == "merged"
    assert g.read_text(encoding="utf-8").startswith("*.log\n\n# >>> python-repo-template")
    assert cm.managed_block(g, rules, NAME, []) == "current"


def test_managed_block_replaces_in_place(tmp_path: Path) -> None:
    rules = tmp_path / "rules"
    rules.write_text("new\n", encoding="utf-8")
    old = cm.merge_block("mine\n", "old", NAME) + "after\n"
    assert cm.merge_block(old, "new", NAME) == cm.merge_block("mine\n", "new", NAME) + "after\n"


def test_managed_block_wraps_a_seedless_copy_and_dedupes() -> None:
    assert cm.merge_block("a\n", "a", NAME) == cm.merge_block("", "a", NAME)
    doubled = "a\n\n" + cm.merge_block("", "a", NAME)
    assert cm.merge_block(doubled, "a", NAME) == cm.merge_block("", "a", NAME)


def test_template_gitignore_is_the_merge_of_the_rules() -> None:
    rules = (ROOT / "gitignore.rules").read_text(encoding="utf-8")
    have = (ROOT / "template" / ".gitignore").read_text(encoding="utf-8")
    assert cm.merge_block("", rules, NAME) == have


# --- recipes ------------------------------------------------------------------



def test_recipe_match_is_whole_lines() -> None:
    assert cm.find_block("xtest:\n    a\n", "test:\n    a") == -1
    assert cm.find_block("test:\n    a\n    b\n", "test:\n    a") == -1
    assert cm.find_block("test:\n    a\n\n", "test:\n    a") == 0


# --- main / argv ----------------------------------------------------------------


def test_main_runs_each_verb(tmp_path: Path) -> None:
    f = tmp_path / "justfile"
    f.write_text("OLD-A\n", encoding="utf-8")
    assert cm.main(["swap", str(f), "--spec", str(write_spec(tmp_path, SWAP))]) == 0
    assert f.read_text(encoding="utf-8") == "NEW\n"
    rules = tmp_path / "rules"
    rules.write_text("r\n", encoding="utf-8")
    g = tmp_path / ".gitignore"
    assert cm.main(["managed-block", str(g), "--rules", str(rules), "--name", NAME]) == 0
    assert g.exists()


def test_main_bad_spec_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "s.json"
    bad.write_text("[1]", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cm.main(["retire", str(tmp_path / "x"), "--spec", str(bad)])
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        cm.main(["retire", str(tmp_path / "x"), "--spec", str(tmp_path / "missing.json")])
    with pytest.raises(SystemExit):
        cm.strs({"k": [1]}, "k")


# --- the atom law on copier.yml ---------------------------------------------------

INLINE = re.compile(r"<<'|python3? -c|python3 -\s|bash -c|sh -c")


def migrations_block() -> str:
    text = (ROOT / "copier.yml").read_text(encoding="utf-8")
    return text[text.index("\n_migrations:") :]


def test_no_migration_carries_inline_code() -> None:
    body = "\n".join(
        ln for ln in migrations_block().splitlines() if not ln.lstrip().startswith("#")
    )
    assert not INLINE.search(body)


def test_every_migration_runs_the_committed_tool() -> None:
    body = migrations_block()
    commands = re.findall(r"^    command:\s*(.*)$", body, re.MULTILINE)
    assert commands, "no migration commands found"
    for c in commands:
        assert c.startswith('[python3, "{{ _copier_conf.src_path }}/tools/copier_migrate.py"')


def test_every_spec_a_migration_names_exists() -> None:
    for ref in re.findall(r"migrations/([\w.-]+\.json)", migrations_block()):
        assert (MIG / ref).is_file(), ref


# --- v0.44.2: sys.argv leaves the command-injection sources ---------------------

SAST = ROOT / "template" / "rules" / "sast" / "dataflow.yml"


def test_sast_argv_swap_lands_on_the_template_rules(tmp_path: Path) -> None:
    """Un-doing the swap on today's rules and re-running it restores them exactly."""
    s = spec("v0.44.2-sast-argv.json")
    today = SAST.read_text(encoding="utf-8")
    new = cm.strs(s, "new")[0]
    assert today.count(new) == 1
    f = tmp_path / "dataflow.yml"
    f.write_text(today.replace(new, cm.strs(s, "old")[0]), encoding="utf-8")
    assert "- pattern: sys.argv" in f.read_text(encoding="utf-8")
    assert cm.swap(f, s) == "swept"
    assert f.read_text(encoding="utf-8") == today
    assert cm.swap(f, s) == "current"


def test_sast_argv_swap_leaves_an_edited_rule(tmp_path: Path) -> None:
    s = spec("v0.44.2-sast-argv.json")
    f = tmp_path / "dataflow.yml"
    f.write_text("rules:\n  - id: forge-taint-command-injection\n    edited: true\n", "utf-8")
    assert cm.swap(f, s) == "kept"


def test_sast_argv_swap_is_wired_in_copier_yml() -> None:
    assert re.search(
        r"version: v0\.44\.2\n\s+when:.*\n\s+command: \[.*swap, rules/sast/dataflow\.yml, "
        r"--spec, .*v0\.44\.2-sast-argv\.json",
        migrations_block(),
    )
