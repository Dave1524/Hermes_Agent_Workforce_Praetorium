#!/usr/bin/env python3
"""Tier 2 — grounding regression: does the vault still answer the questions it got wrong?

usage: fleet_eval_grounding.py [--probes FILE] [--index FILE] [--team FILE] [--skip-probes]

Emits one `check|status|value|detail` row per assertion on stdout. Exit 1 on any FAIL.

WHAT THIS MEASURES, AND WHAT IT DOES NOT. Retrieval is only half of grounding: the
other half is the TEAM.md instruction layer, which reaches every turn regardless of what
`query` ranks first. A probe that FAILs means retrieval alone will not save the agent on
that wording — it does NOT mean the agent answers wrong, because the instruction layer
still points at the anchor. That is why `team_instructions` is the hard gate and the
probes gate on regression against a recorded baseline.

FRESHNESS FIRST. Every probe below is a measurement of the index, so a stale index
measures the wrong system entirely. The sweep compares each file's sha256 against the
`documents.hash` column — qmd stores the plain sha256 of the file bytes, so this is
exact rather than an mtime heuristic. A stale anchor invalidates the probes instead of
failing them: a wrong answer and an unasked question are different results.
"""

import argparse
import fnmatch
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

DEFAULT_INDEX = Path.home() / ".cache/qmd/index.sqlite"
DEFAULT_PROBES = Path(__file__).resolve().parent / "fleet_eval_probes.json"
DEFAULT_TEAM = Path.home() / ".config/buzz-team/TEAM.md"
COLLECTION = "vault"
QUERY_TIMEOUT_SECS = 300

# PASS beats POINTER beats FAIL. A probe regresses when it scores below its baseline.
RANK = {"FAIL": 0, "POINTER": 1, "PASS": 2}

# `@@ -84,3 @@ (83 before, 0 after)` — the hunk header is the retrieved chunk (line 84,
# 3 lines). The parenthesised pair is the REST of the document, not part of the chunk:
# that file is 85 lines, and 83 + 3 + 0 accounts for all of it. Reading the pair as the
# chunk's context window reconstructs nearly the whole document and turns every probe
# into a POINTER, which is how this check first reported a false improvement.
SPAN = re.compile(r"@@ -(\d+),(\d+) @@")


class Report:
    """Collects rows and owns the exit code, so no assertion can fail silently."""

    def __init__(self):
        self.rows = []
        self.failed = False

    def add(self, check, status, value="", detail=""):
        self.rows.append((check, status, str(value), detail))
        self.failed = self.failed or status == "FAIL"

    def emit(self):
        for row in self.rows:
            print("|".join(row))


def collection_root(index):
    db = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    name, path, pattern, ignores = db.execute(
        "select name, path, pattern, ignore_patterns from store_collections where name = ?",
        (COLLECTION,),
    ).fetchone()
    return Path(path), pattern, json.loads(ignores)


def indexed_hashes(index):
    db = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    return dict(
        db.execute(
            "select path, hash from documents where collection = ? and active = 1",
            (COLLECTION,),
        )
    )


def _ignored(relative, ignores):
    return any(part.startswith(".") for part in Path(relative).parts) or any(
        fnmatch.fnmatch(relative, pattern) for pattern in ignores
    )


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_index_path(relative):
    """qmd rewrites `_` and ` ` to `-` in every path component. Verified over all 477."""
    return relative.replace("_", "-").replace(" ", "-")


def _disk_documents(root, pattern, ignores):
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.glob(pattern))
        if not _ignored(str(path.relative_to(root)), ignores)
    }


def check_freshness(report, index, anchor_disk):
    """Does the index hold the bytes that are on disk right now?

    qmd stores the plain sha256 of the file, so this is exact. mtime is not usable in
    either direction: a WAL read bumps the index file's own mtime, which would report a
    stale index as fresh — the dangerous direction for a suite whose whole job is to
    notice staleness.
    """
    root, pattern, ignores = collection_root(index)
    indexed = indexed_hashes(index)
    on_disk = _disk_documents(root, pattern, ignores)

    drifted = [
        relative
        for relative, path in on_disk.items()
        if as_index_path(relative) in indexed
        and _sha256(path) != indexed[as_index_path(relative)]
    ]
    deleted = sorted(set(indexed) - {as_index_path(r) for r in on_disk})

    anchor_stale = str(anchor_disk) in drifted
    if anchor_stale:
        report.add(
            "index-freshness", "FAIL", len(drifted),
            f"the anchor is indexed at older content — the probes below would measure the "
            f"previous vault. Run `systemctl start qmd-refresh` and re-run.",
        )
    elif drifted or deleted:
        report.add(
            "index-freshness", "WARN", len(drifted) + len(deleted),
            f"{len(drifted)} documents changed since indexing, {len(deleted)} indexed but gone "
            f"(anchor is current, so the probes still hold): {', '.join((drifted + deleted)[:3])}",
        )
    else:
        report.add(
            "index-freshness", "PASS", len(indexed),
            f"{len(indexed)} documents, every one indexed at its current content",
        )
    return not anchor_stale


def check_coverage(report, index, baseline):
    """Files qmd never picked up — a count, because the walker's rules are its own.

    Four vendored skill files under `08_skills/vp-pitch-deck/vendor/` have sat unindexed
    since 2026-07-27 and are not a freshness fault. Baselining the count keeps that quiet
    while still surfacing the fifth one, which would be a document nobody can retrieve.
    """
    root, pattern, ignores = collection_root(index)
    indexed = indexed_hashes(index)
    missing = sorted(
        relative
        for relative in _disk_documents(root, pattern, ignores)
        if as_index_path(relative) not in indexed
    )

    status = "PASS" if len(missing) <= baseline else "WARN"
    report.add(
        "index-coverage", status, len(missing),
        f"{len(missing)} of {len(missing) + len(indexed)} vault documents are not in the index "
        f"(baseline {baseline}): {', '.join(missing[:4])}" if missing else "every document indexed",
    )


def check_anchor(report, index, anchor):
    """Both path spellings must resolve — they differ, and the error looks identical."""
    root, _, _ = collection_root(index)
    on_disk = root / anchor["disk"]
    if on_disk.is_file():
        report.add("anchor-on-disk", "PASS", on_disk.stat().st_size, str(on_disk))
    else:
        report.add("anchor-on-disk", "FAIL", 0, f"{on_disk} does not exist")

    body = qmd_get(f"{COLLECTION}/{anchor['index']}")
    if body:
        report.add("anchor-in-index", "PASS", len(body.splitlines()), anchor["index"])
    else:
        report.add("anchor-in-index", "FAIL", 0, f"qmd get returned nothing for {anchor['index']}")


def check_team_instructions(report, team_file, spec, root):
    """The instruction layer is what carries a question retrieval ranks wrong."""
    if not team_file.is_file():
        report.add("team-grounding-section", "FAIL", 0, f"{team_file} does not exist")
        return

    text = team_file.read_text()
    if spec["section"] in text:
        report.add("team-grounding-section", "PASS", 1, spec["section"])
    else:
        report.add(
            "team-grounding-section", "FAIL", 0,
            f"TEAM.md no longer carries the section '{spec['section']}' — the fleet's only "
            f"retrieval-independent pointer to the anchor is gone",
        )

    named = spec["must_name"]
    if named not in text:
        report.add("team-names-anchor", "FAIL", 0, f"TEAM.md does not name {named}")
    elif (root / named).is_file():
        report.add("team-names-anchor", "PASS", 1, named)
    else:
        report.add("team-names-anchor", "FAIL", 0, f"TEAM.md names {named}, which does not exist on disk")


def check_census(report, root, spec):
    """Trend: documents in the project folder that have never heard of the migration."""
    folder = root / spec["dir"]
    if not folder.is_dir():
        report.add("staleness-census", "FAIL", 0, f"{folder} does not exist")
        return

    term = re.compile(spec["term"])
    unaware = sorted(p.name for p in folder.glob("*.md") if not term.search(p.read_text()))
    baseline = spec["baseline_unaware"]
    status = "PASS" if len(unaware) <= baseline else "WARN"
    trend = "unchanged" if len(unaware) == baseline else f"was {baseline}"
    report.add(
        "staleness-census", status, len(unaware),
        f"{len(unaware)} of {len(list(folder.glob('*.md')))} documents never mention the "
        f"migration ({trend}): {', '.join(unaware[:4])}",
    )


def qmd(args):
    result = subprocess.run(
        ["qmd", *args], capture_output=True, text=True, timeout=QUERY_TIMEOUT_SECS
    )
    return result.stdout if result.returncode == 0 else ""


def qmd_get(path_with_span):
    return qmd(["get", path_with_span])


def run_query(probe):
    document = "\n".join(f"{s['type']}: {s['query']}" for s in probe["searches"])
    raw = qmd(["query", document, "--format", "json", "-n", str(probe["limit"])])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _rank_of(results, anchor_index):
    needle = f"{COLLECTION}/{anchor_index}"
    for position, hit in enumerate(results, start=1):
        if hit.get("file", "").endswith(needle):
            return position
    return None


def _span_carries_pointer(hit, pointer):
    """Would the pointer be inside the chunk the agent actually receives?

    A supersession banner at the top of a document is invisible when the retrieved
    chunk sits 80 lines below it — that is exactly how agent-inbox-sync/SKILL.md kept
    winning this question after being bannered. The chunk, not the document, is the
    honest unit: the agent is handed the chunk and has no reason to fetch the rest.

    The snippet text is truncated for display, so the chunk is re-read at its exact
    line range rather than pattern-matched against the preview.
    """
    snippet = hit.get("snippet", "")
    match = SPAN.search(snippet)
    if not match:
        return bool(re.search(pointer, snippet))
    start, count = int(match.group(1)), int(match.group(2))
    path = hit.get("file", "").replace("qmd://", "")
    return bool(re.search(pointer, qmd_get(f"{path}:{start}:{count}")))


def run_probe(report, probe, anchor):
    results = run_query(probe)
    if results is None:
        report.add(f"probe/{probe['id']}", "FAIL", "", "qmd query returned no parseable result")
        return

    rank = _rank_of(results, anchor["index"])
    top = results[0] if results else {}
    top_name = Path(top.get("file", "?")).name

    if rank is not None and rank <= probe["max_rank"]:
        verdict, detail = "PASS", f"anchor at rank {rank} (max {probe['max_rank']})"
    elif top and _span_carries_pointer(top, anchor["pointer"]):
        verdict = "POINTER"
        detail = f"anchor at rank {rank or 'absent'}; {top_name} wins but its retrieved span points here"
    else:
        verdict = "FAIL"
        detail = f"anchor at rank {rank or 'absent'}; {top_name} wins and its retrieved span does not point here"

    baseline = probe["baseline"]
    if RANK[verdict] < RANK[baseline]:
        status, note = "FAIL", f"REGRESSION from {baseline} — {detail}"
    elif RANK[verdict] > RANK[baseline]:
        status, note = "PASS", f"improved on baseline {baseline} (bump the fixture) — {detail}"
    else:
        status, note = "PASS", f"at baseline {baseline} — {detail}"

    report.add(f"probe/{probe['id']}", status, verdict, note)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probes", type=Path, default=DEFAULT_PROBES)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--team", type=Path, default=DEFAULT_TEAM)
    parser.add_argument("--skip-probes", action="store_true",
                        help="structural assertions only; skips the ~2min of local reranking")
    args = parser.parse_args()

    fixture = json.loads(args.probes.read_text())
    anchor = fixture["anchor"]
    report = Report()
    root, _, _ = collection_root(args.index)

    fresh = check_freshness(report, args.index, anchor["disk"])
    check_coverage(report, args.index, fixture["index"]["unindexed_baseline"])
    check_anchor(report, args.index, anchor)
    check_team_instructions(report, args.team, fixture["team_instructions"], root)
    check_census(report, root, fixture["census"])

    for probe in fixture["probes"]:
        if args.skip_probes:
            report.add(f"probe/{probe['id']}", "SKIP", "", "--skip-probes")
        elif not fresh:
            report.add(f"probe/{probe['id']}", "SKIP", "", "index is stale at the anchor — not measured")
        else:
            run_probe(report, probe, anchor)

    report.emit()
    return 1 if report.failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, sqlite3.Error, subprocess.TimeoutExpired, ValueError) as error:
        print(f"grounding|FAIL||{error}")
        sys.exit(1)
