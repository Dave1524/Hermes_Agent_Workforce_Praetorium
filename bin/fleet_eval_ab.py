#!/usr/bin/env python3
"""Tier 2 — A/B a proposed vault edit against the grounding probes before promoting it.

usage: fleet_eval_ab.py --edits FILE [--scratch DIR] [--keep]

Answers one question: if this edit landed on canonical, what would the probes do?
Prints a per-check control/treatment table and exits 1 if any check regresses.

WHY THIS EXISTS. On 2026-08-17 a two-index experiment decided p2_publish_approve's
baseline, correctly predicted the live result after the merge, and left nothing behind
to rerun — it was done by hand. The fixture's own `why` block now cites controlled
experiments as its evidence standard, so the method needs to be reproducible or the
standard is a claim about a session nobody can repeat.

ONE VARIABLE, AND THE RUN PROVES IT. Both arms come from a WAL-consistent `.backup` of
the live index, not a fresh build, and the collection is repointed at an rsync of the
vault. Every unchanged document therefore keeps its existing embedding byte-for-byte
and `qmd update` re-embeds only what the edit touched. That is stronger than two
independent full builds: build conditions cannot drift because there is only one build.
The run asserts it — `1 updated, N unchanged` is checked, not assumed.

THE CONTROL MUST REPRODUCE LIVE FIRST. A scratch arm that disagrees with the live index
before any edit is applied is measuring something else, and every conclusion drawn from
it is void. That check runs first and aborts the comparison.

EDIT SHAPES ARE THE FOUR THAT MOVE CHUNKS. `append` adds a section at the end of a
file, which re-cuts nothing below it because there is nothing below it. `append_to_line`
extends an existing line so the text joins that line's chunk instead of forming its own
— the difference between being retrieved with a paragraph and competing against it.
`replace_block` swaps a run of lines in place. `substitute` rewrites one unique substring,
for a rename that has to land inside a paragraph; it must match exactly once, because a
rename that silently hits two sites is the failure it exists to prevent. Inserting before
existing prose has no shape of its own — express it as a `replace_block` that re-emits the
anchor, so the insert is visible in the spec rather than implied. Every shape but the first
re-cuts the spans below it, which is the whole reason to measure instead of reasoning.
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "fleet_eval_grounding.py"
LIVE_INDEX = Path.home() / ".cache/qmd/index.sqlite"
LIVE_CONFIG = Path.home() / ".config/qmd/index.yml"
VAULT_SYMLINK = Path.home() / "vault"
COLLECTION = "vault"
RANK = {"FAIL": 0, "WARN": 1, "POINTER": 1, "PASS": 2}


def run(cmd, env=None, timeout=1800):
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=timeout
    )
    if result.returncode not in (0, 1):
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{result.stderr}")
    return result.stdout


def build_arm(scratch):
    """Snapshot the live index and repoint it at a private copy of the vault."""
    vault, cfg = scratch / "vault", scratch / "cfg"
    if scratch.exists():
        shutil.rmtree(scratch)
    vault.mkdir(parents=True)
    cfg.mkdir(parents=True)
    run(["rsync", "-a", "--exclude", ".git", f"{VAULT_SYMLINK.resolve()}/", str(vault)])
    source, snapshot = sqlite3.connect(LIVE_INDEX), sqlite3.connect(cfg / "index.sqlite")
    source.backup(snapshot)
    source.close()
    snapshot.close()
    db = sqlite3.connect(cfg / "index.sqlite")
    db.execute(
        "update store_collections set path = ? where name = ?", (str(vault), COLLECTION)
    )
    db.commit()
    db.close()
    (cfg / "index.yml").write_text(
        LIVE_CONFIG.read_text().replace(
            f"path: {VAULT_SYMLINK}", f"path: {vault}"
        )
    )
    return vault, cfg


def arm_env(cfg):
    return {
        **os.environ,
        "QMD_CONFIG_DIR": str(cfg),
        "INDEX_PATH": str(cfg / "index.sqlite"),
    }


def apply_edit(vault, edit):
    path = vault / edit["path"]
    text = path.read_text()
    if "append" in edit:
        path.write_text(text.rstrip("\n") + "\n" + edit["append"])
        return
    if "substitute" in edit:
        path.write_text(_substitute(text, edit["substitute"], edit["path"]))
        return
    lines = text.split("\n")
    start = _find(lines, edit["anchor"], edit["path"])
    if "append_to_line" in edit:
        lines[start] += edit["append_to_line"]
    else:
        end = _find(lines[start:], edit["until"], edit["path"], start)
        lines[start : end + 1] = edit["replace_block"].split("\n")
    path.write_text("\n".join(lines))


def _substitute(text, spec, where):
    hits = text.count(spec["from"])
    if hits != 1:
        sys.exit(f"substitute matched {hits}x in {where}, need exactly 1: {spec['from']!r}")
    return text.replace(spec["from"], spec["to"])


def _find(lines, needle, where, offset=0):
    for n, line in enumerate(lines, offset):
        if line.startswith(needle) or line.endswith(needle):
            return n
    sys.exit(f"anchor not found in {where}: {needle!r}")


def reindex(env, expected):
    """Re-embed only what changed, and fail loudly if more than that moved."""
    out = run(["qmd", "update"], env=env)
    match = re.search(r"(\d+) new, (\d+) updated, (\d+) unchanged", out)
    if not match:
        sys.exit(f"could not read qmd update output:\n{out}")
    new, updated, unchanged = map(int, match.groups())
    if new or updated != expected:
        sys.exit(
            f"edit touched {new} new + {updated} updated documents, expected "
            f"{expected} updated — the arms differ by more than the edit"
        )
    run(["qmd", "embed"], env=env)
    return unchanged


def probe(index, env):
    rows = {}
    for line in run(
        [sys.executable, str(RUNNER), "--index", str(index)], env=env
    ).splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            rows[parts[0]] = (parts[1], parts[2])
    return rows


def compare(control, treatment):
    """Gate on the status column, display the value column.

    Only status carries direction. `value` is a verdict for probes but a raw count
    for the census checks, where lower is better for staleness and a fixed baseline
    is better for coverage — ranking those as verdicts scores every one of them 0
    and silently passes a regression, which is how this function first read a
    staleness rise as no change at all.
    """
    regressed = False
    width = max(len(k) for k in control)
    for check, (status, before) in control.items():
        after_status, after = treatment.get(check, ("?", "?"))
        delta = RANK.get(after_status, -1) - RANK.get(status, -1) or _probe_delta(
            check, before, after
        )
        mark = "  " if not delta else ("UP" if delta > 0 else "!!")
        regressed |= delta < 0
        if before != after or check.startswith("probe/"):
            print(f"{mark} {check:<{width}}  {before:>7} -> {after}")
    return regressed


def _probe_delta(check, before, after):
    """A probe can improve while its status stays PASS — it passed its baseline both times."""
    if not check.startswith("probe/"):
        return 0
    return RANK.get(after, -1) - RANK.get(before, -1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--edits", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/fleet-eval-ab"))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    edits = json.loads(args.edits.read_text())
    vault, cfg = build_arm(args.scratch)

    live = probe(LIVE_INDEX, os.environ)
    control = probe(cfg / "index.sqlite", arm_env(cfg))
    drifted = [k for k in control if control[k][1] != live.get(k, ("", ""))[1]]
    if drifted:
        sys.exit(f"scratch control disagrees with live on {drifted} — arm not comparable")
    print(f"control reproduces live ({len(control)} checks)\n")

    for edit in edits:
        apply_edit(vault, edit)
    unchanged = reindex(arm_env(cfg), expected=len({e["path"] for e in edits}))
    print(f"applied {len(edits)} edit(s), {unchanged} documents identical\n")

    regressed = compare(control, probe(cfg / "index.sqlite", arm_env(cfg)))
    if not args.keep:
        shutil.rmtree(args.scratch)
    sys.exit(1 if regressed else 0)


if __name__ == "__main__":
    main()
