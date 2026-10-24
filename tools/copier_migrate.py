# SPDX-FileCopyrightText: 2026 Rob Fischer
#
# SPDX-License-Identifier: Apache-2.0

"""copier_migrate: the one command every `_migrations` entry runs.

copier.yml calls this file by path, as argv, with no inline code (Rob's atom
law): ``python3 {{ _copier_conf.src_path }}/tools/copier_migrate.py <verb> ...``.
It runs inside the destination tree at the `after` stage. The payload of each
migration is data under ``migrations/`` (JSON), never code in the YAML.

Verbs (each idempotent, each exits 0 when it leaves a file alone):

  retire PATH --spec S         delete PATH when its sha256 is in S["sha256"]
  swap PATH --spec S           replace the first S["old"] block with S["new"]
  managed-block PATH --rules R --name N
                               merge R into PATH as N's managed block
  recipes PATH --spec S        recipe-level exact-match justfile sweep
  referee PATH --prev P        put the star's own package.json keys back
                               after an update (P: the pre-update copy)

THIS FILE IS VENDORED, byte-identical, in python-, go-, rust- and frontend-repo-
template (a template cannot import across repos). tools/test_copier_migrate_core.py
pins its sha256, so a lone edit fails there. Change all four copies together.

EXACT MATCH, NEVER A GUESS. A file that matches no shape the template shipped
is named and left alone; the star reconciles it by hand. Exit 2 is reserved for
a bad invocation or an unreadable spec, so a broken migration fails loudly.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import cast

PREFIX = "copier: "


def say(msg: str) -> None:
    """Print one copier-prefixed line."""
    print(PREFIX + msg)


def load_spec(path: Path) -> dict[str, object]:
    """Read a migration spec (a JSON object).

    Raises:
        SystemExit: the spec is unreadable or not an object (exit 2).

    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"{PREFIX}cannot read spec {path}: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    if not isinstance(data, dict):
        print(f"{PREFIX}spec {path} is not a JSON object", file=sys.stderr)
        raise SystemExit(2)
    return cast("dict[str, object]", data)


def strs(spec: dict[str, object], key: str) -> list[str]:
    """Spec field as a list of strings (a bare string is a one-item list)."""
    v = spec.get(key, [])
    if isinstance(v, str):
        return [v]
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        print(f"{PREFIX}spec field {key!r} must be a string list", file=sys.stderr)
        raise SystemExit(2)
    return cast("list[str]", v)


def retire(target: Path, spec: dict[str, object]) -> str:
    """Delete target when it is byte-identical to a shipped rendering.

    A spec ``epilogue`` is printed whatever the outcome.
    """
    outcome = retire_outcome(target, spec)
    if "epilogue" in spec:
        say(str(spec["epilogue"]))
    return outcome


def retire_outcome(target: Path, spec: dict[str, object]) -> str:
    """Do the retire and name what happened."""
    if not target.exists():
        return "absent"
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest in set(strs(spec, "sha256")):
        target.unlink()
        say(f"deleted {target} - a rendering this template shipped. " + str(spec.get("note", "")))
        return "deleted"
    say(
        f"{target} matches no rendering the templates shipped (sha256 {digest[:12]}) - "
        "LEAVING IT ALONE. Retire it by hand."
    )
    return "kept"


def swap(target: Path, spec: dict[str, object]) -> str:
    """Replace the first prior block with the new one (substring, once)."""
    label = str(spec.get("label", "block"))
    if not target.exists():
        say(f"no {target} here - nothing to sweep")
        return "absent"
    text = target.read_text(encoding="utf-8")
    new = strs(spec, "new")[0]
    if new in text:
        say(f"the {label} is already current")
        return "current"
    for old in strs(spec, "old"):
        if old in text:
            target.write_text(text.replace(old, new, 1), encoding="utf-8")
            say(f"swept the {label}. " + str(spec.get("note", "")))
            return "swept"
    say(
        f"the {label} matches no shape this template shipped - LEAVING IT ALONE. "
        f"Reconcile by hand against {spec.get('version', 'the template')}."
    )
    return "kept"


def merge_block(cur: str, rules: str, name: str) -> str:
    """Return cur with rules as name's managed block (outside it untouched)."""
    opener = f"# >>> {name} — managed block, edits here are overwritten >>>"
    closer = f"# <<< {name} <<<"
    rules = rules.rstrip("\n")
    block = f"{opener}\n{rules}\n{closer}\n"
    if opener in cur and closer in cur:
        head, rest = cur.split(opener, 1)
        _, tail = rest.split(closer, 1)
        if head.strip("\n") == rules:
            head = ""
        return head + block + tail.lstrip("\n")
    if cur.strip("\n") == rules:
        return block
    return (cur.rstrip("\n") + "\n\n" if cur.strip() else "") + block


def managed_block(target: Path, rules: Path, name: str, notes: list[str]) -> str:
    """Merge the template's rules file into target's managed block."""
    cur = target.read_text(encoding="utf-8") if target.exists() else ""
    new = merge_block(cur, rules.read_text(encoding="utf-8"), name)
    if new == cur:
        say(f"{target} managed block already current")
        return "current"
    target.write_text(new, encoding="utf-8")
    say(f"{target} <- template rules merged (managed block)")
    for n in notes:
        say(n)
    return "merged"


def find_block(text: str, old: str) -> int:
    """Index of old as whole lines ending a recipe, or -1."""
    i = text.find(old)
    while i >= 0:
        after = text[i + len(old) :]
        starts = i == 0 or text[i - 1] == "\n"
        ends = after == "" or (after[0] == "\n" and (len(after) == 1 or after[1] not in " \t"))
        if starts and ends:
            return i
        i = text.find(old, i + 1)
    return -1


def drop_own_attrs(head: str) -> str:
    """Strip the [doc(...)] / [positional-arguments] lines just above a recipe."""
    lines = head.split("\n")
    while len(lines) > 1 and (
        lines[-2].startswith("[doc(") or lines[-2] == "[positional-arguments]"
    ):
        lines.pop(-2)
    return "\n".join(lines)


def sweep_pairs(
    text: str, pairs: list[dict[str, object]], spec: dict[str, object]
) -> tuple[str, list[str], list[str]]:
    """Apply each recipe pair; return (text, swept names, edited names).

    A pair is done when any of its ``new`` blocks is present, or, with the spec's
    ``done_new`` index, when that one is. ``keep_attrs`` leaves the [doc(...)] lines
    above a replaced recipe in place.
    """
    swept: list[str] = []
    kept: list[str] = []
    done = spec.get("done_new")
    for pr in pairs:
        name = str(pr.get("name", "?"))
        news = strs(pr, "new")
        marks = [news[done]] if isinstance(done, int) else news
        if any(n in text for n in marks):
            continue
        for old, new in zip(strs(pr, "old"), news, strict=True):
            i = find_block(text, old)
            if i >= 0:
                head = text[:i] if spec.get("keep_attrs") else drop_own_attrs(text[:i])
                text = head + new + text[i + len(old) :]
                swept.append(name)
                break
        else:
            kept.append(name)
    return text, swept, kept


def gate(text: str, base: Path, spec: dict[str, object]) -> str | None:
    """Return the reason to leave the justfile alone, or None to sweep it."""
    done = spec.get("done_if")
    if isinstance(done, str) and re.search(done, text, re.MULTILINE):
        return f"justfile already matches {done!r}"
    need = spec.get("need_re")
    if isinstance(need, str) and not re.search(need, text, re.MULTILINE):
        return f"justfile does not match {need!r} yet - LEAVING IT ALONE (an earlier sweep first)."
    for req in strs(spec, "require"):
        if not (base / req).exists():
            return f"no {req} beside the justfile yet - LEAVING IT ALONE (the next update retries)."
    for bad in strs(spec, "refuse"):
        if bad in text:
            return (
                f"justfile carries {bad.strip()!r} of its own - LEAVING IT ALONE (hand-migrated)."
            )
    anchor = spec.get("anchor")
    if isinstance(anchor, str) and anchor not in text:
        return f"justfile has no {anchor.strip()!r} - LEAVING IT ALONE. Reconcile by hand."
    return None


def rewrite_lines(text: str, spec: dict[str, object]) -> str:
    """Apply the spec's ``lines`` rewrites (every occurrence), after a sweep.

    An entry with ``unless`` is skipped while that regex still matches the text:
    a recipe the sweep kept still reads what the rewrite would remove.
    """
    entries = spec.get("lines", [])
    if not isinstance(entries, list):
        raise SystemExit(2)
    for ent in cast("list[dict[str, str]]", entries):
        guard = ent.get("unless")
        if guard is not None and re.search(guard, text):
            continue
        text = text.replace(ent["old"], ent["new"])
    return text


def recipes(target: Path, spec: dict[str, object]) -> str:
    """Sweep recipes by exact match, then insert the import after the anchor.

    No `just --list` re-parse (the go template's inline sweep runs one): ruff's
    S603 refuses a subprocess call here, and a suppression is not an option.
    Exact match is the guard instead: every write puts a block the template
    pours today in place of one it poured before, so the result parses
    whenever the input did.
    """
    if not target.exists():
        say(f"no {target} here - nothing to sweep")
        return "absent"
    orig = target.read_text(encoding="utf-8")
    why = gate(orig, target.parent, spec)
    if why is not None:
        say(why)
        return "gated"
    pairs = spec.get("pairs", [])
    if not isinstance(pairs, list):
        raise SystemExit(2)
    text, swept, kept = sweep_pairs(orig, cast("list[dict[str, object]]", pairs), spec)
    if not swept:
        if kept:
            say("no recipe matched a shipped block - LEFT ALONE. EDITED: " + ", ".join(kept))
        return "kept"
    text = rewrite_lines(text, spec)
    anchor, insert = spec.get("anchor"), spec.get("insert")
    if isinstance(anchor, str) and isinstance(insert, str):
        text = text.replace(anchor, anchor + "\n" + insert, 1)
    target.write_text(text, encoding="utf-8")
    say("swept: " + ", ".join(swept))
    if kept:
        say("EDITED, LEFT ALONE (reconcile by hand): " + ", ".join(kept))
    return "swept"


OWNED = (
    "version",
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
    "overrides",
    "engines",
)


def referee(target: Path, prev: Path) -> str:
    """Put the star's own package.json keys back after an update merged over them.

    ``prev`` is the package.json as it stood before the update (the migration
    before this one checks it out of the index). It is deleted when read.
    """
    try:
        return referee_keys(target, prev)
    finally:
        prev.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            prev.parent.rmdir()


def referee_keys(target: Path, prev: Path) -> str:
    """Restore the OWNED keys of ``prev`` into ``target``, in the star's key order."""
    try:
        prev_raw = prev.read_text(encoding="utf-8")
    except OSError:
        say("no package.json at HEAD - nothing to referee")
        return "absent"
    try:
        before = json.loads(prev_raw)
        merged = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(before, dict) or not isinstance(merged, dict):
            raise TypeError("not a JSON object")
    except (OSError, ValueError, TypeError) as e:
        say(f"package.json does not parse ({e}).")
        say(
            "leaving it ALONE - resolve the conflict, then re-check "
            "that version/dependencies/devDependencies/overrides still hold."
        )
        return "kept"
    restored = [k for k in OWNED if k in before and merged.get(k) != before[k]]
    for k in restored:
        merged[k] = before[k]
    out = {k: merged[k] for k in before if k in merged}
    out.update((k, v) for k, v in merged.items() if k not in out)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    if restored:
        say("star-owned package.json keys kept: " + ", ".join(restored))
        say("run `bun install` - the lockfile may now be stale.")
        return "restored"
    say("package.json needed no refereeing")
    return "clean"


def parser() -> argparse.ArgumentParser:
    """Build the argv surface."""
    p = argparse.ArgumentParser(
        prog="copier_migrate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="verb", required=True)
    for verb in ("retire", "swap", "recipes"):
        s = sub.add_parser(verb)
        s.add_argument("path", type=Path)
        s.add_argument("--spec", type=Path, required=True)
    m = sub.add_parser("managed-block")
    m.add_argument("path", type=Path)
    m.add_argument("--rules", type=Path, required=True)
    m.add_argument("--name", required=True)
    m.add_argument("--note", action="append", default=[])
    r = sub.add_parser("referee")
    r.add_argument("path", type=Path)
    r.add_argument("--prev", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    """Run one verb; 0 unless the invocation itself is wrong."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    a = parser().parse_args(argv)
    if a.verb == "managed-block":
        managed_block(a.path, a.rules, a.name, a.note)
        return 0
    if a.verb == "referee":
        referee(a.path, a.prev)
        return 0
    verbs = {"retire": retire, "swap": swap, "recipes": recipes}
    verbs[a.verb](a.path, load_spec(a.spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
