#!/usr/bin/env python3
"""Three SDLC numbers per landed brief, read from the ship-dev-plan LAND records (T8.7).

    sdlc_measurements.py --repo PATH [--since DATE] [--runs GLOB] [--markdown --today DATE]

One row per commit that renames a brief into .claude/briefs/archive/. A row is a LAND record
only when the archive commit's body carries `verifyExit:`; every other row reads
`record: none` with `-` in each numeric column, never a defaulted success.

- first_pass / rework / harness: from the Workflow run records when --runs is given (every
  `land:<id>` attempt, ordered by start), else from the git proxy (commits between the brief's
  first commit and the archive: one means first pass, each further one is a rework). The
  column header says which source produced it; where both exist and disagree, a WARN line.
- plan_fidelity: file-set overlap between the brief's Files sections and what the range
  touched. A stand-in for the playbook's plan fidelity, not the thing itself.
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import re
import shlex
import subprocess
import sys

ARCHIVE_DIR = ".claude/briefs/archive/"
BRIEF_RE = re.compile(r"^\.claude/briefs/[^/]+\.md$")
FILES_HEADING = re.compile(r"^## Files to (modify|create|delete)\b")
ID_FROM_SUBJECT = re.compile(r"\barchive (?:the )?(T\d+(?:\.\d+)?[a-z]?)\b")
ID_FROM_SLUG = re.compile(r"^t(\d+)-(\d+)([a-z]?)-")
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
HARNESS_MARKERS = ("returned null", "did not return", "not landed:")
SHIP_WORKFLOW = "ship-dev-plan"


@dataclasses.dataclass
class Archive:
    sha: str
    date: str
    subject: str
    body: str
    source: str
    target: str


@dataclasses.dataclass
class Row:
    task: str
    archive: Archive
    record: dict | None
    range_first: str | None = None
    commits: int | None = None
    attempts: list[str] = dataclasses.field(default_factory=list)
    landed_by: str | None = None
    named: set[str] = dataclasses.field(default_factory=set)
    touched: set[str] = dataclasses.field(default_factory=set)
    warn: str | None = None


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True).stdout


def renames_into_archive(name_status: str) -> list[tuple[str, str]]:
    pairs = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R") and BRIEF_RE.match(parts[1]) \
                and parts[2].startswith(ARCHIVE_DIR):
            pairs.append((parts[1], parts[2]))
    return pairs


def archive_commits(repo: str, since: str | None) -> list[Archive]:
    args = ["log", "--diff-filter=R", "-M", "--format=%H", *(["--since", since] if since else [])]
    found = []
    for sha in git(repo, *args).split():
        pairs = renames_into_archive(git(repo, "show", "-M", "--name-status", "--format=", sha))
        if not pairs:
            continue
        date, subject = git(repo, "show", "-s", "--format=%ad%x1f%s", "--date=short", sha).strip().split("\x1f", 1)
        body = git(repo, "show", "-s", "--format=%b", sha)
        found += [Archive(sha, date, subject, body, src, dst) for src, dst in pairs]
    return found


def parse_record(body: str) -> dict | None:
    m = re.search(r"^verifyExit:\s*(\S+)", body, re.M)
    return {"verifyExit": m.group(1)} if m else None


def slug_of(archive: Archive) -> str:
    name = archive.target.rsplit("/", 1)[-1][:-3]
    return DATE_PREFIX.sub("", name)


def task_id(archive: Archive) -> str:
    m = ID_FROM_SUBJECT.search(archive.subject)
    if m:
        return m.group(1)
    m = ID_FROM_SLUG.match(slug_of(archive))
    return f"T{m.group(1)}.{m.group(2)}{m.group(3)}" if m else slug_of(archive)


def brief_files(text: str, own_paths: set[str]) -> set[str]:
    named, inside = set(), False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = bool(FILES_HEADING.match(line))
            continue
        path = bullet_path(line) if inside else None
        if path and path not in own_paths:
            named.add(path)
    return named


def bullet_path(line: str) -> str | None:
    m = re.match(r"^- `([^`]+)`", line)
    if not m:
        return None
    path = re.sub(r":\d+(?:[-,]\d+)*$", "", m.group(1).strip())
    return path or None


def first_commit(repo: str, source: str) -> str | None:
    adds = git(repo, "log", "--diff-filter=A", "--format=%H", "--", source).split()
    if len(adds) != 1:
        return None
    added = git(repo, "show", "--diff-filter=A", "--name-only", "--format=", adds[0]).split()
    return adds[0] if sum(bool(BRIEF_RE.match(p)) for p in added) == 1 else None


def git_range(repo: str, row: Row) -> None:
    first = first_commit(repo, row.archive.source)
    if first is None:
        return
    rng = f"{first}^..{row.archive.sha}^"
    row.range_first = first
    row.commits = int(git(repo, "rev-list", "--count", rng).strip())
    changed = git(repo, "diff", "--name-only", f"{first}^", f"{row.archive.sha}^").split()
    row.touched = {p for p in changed if not BRIEF_RE.match(p)}


def load_runs(pattern: str | None) -> list[dict]:
    if not pattern:
        return []
    runs = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            run = json.load(f)
        if run.get("workflowName") == SHIP_WORKFLOW:
            runs.append(run)
    return runs


def attempt_outcome(run: dict, task: str, entry: dict) -> str:
    result = run.get("result") or {}
    if task in {x.get("id") for x in result.get("landed") or []}:
        return "landed"
    if entry.get("state") == "error":
        return "harness"
    if result.get("stoppedAt") != task:
        return "other"
    if not result.get("land") or any(m in (result.get("failingAssertion") or "") for m in HARNESS_MARKERS):
        return "harness"
    return "review" if (result["land"].get("reviewConfirmed") or []) else "other"


def land_attempts(runs: list[dict], task: str) -> list[tuple[int, str]]:
    attempts = []
    for run in runs:
        for entry in run.get("workflowProgress") or []:
            if entry.get("label") == f"land:{task}":
                attempts.append((entry.get("startedAt") or 0, attempt_outcome(run, task, entry)))
    return sorted(attempts)


def measure(repo: str, since: str | None, runs: list[dict]) -> list[Row]:
    rows = []
    for archive in archive_commits(repo, since):
        row = Row(task_id(archive), archive, parse_record(archive.body))
        if row.record:
            fill_record(repo, row, runs)
        rows.append(row)
    return rows


def fill_record(repo: str, row: Row, runs: list[dict]) -> None:
    git_range(repo, row)
    brief = git(repo, "show", f"{row.archive.sha}:{row.archive.target}")
    row.named = brief_files(brief, {row.archive.source, row.archive.target})
    row.attempts = [o for _, o in land_attempts(runs, row.task)]
    landed = any(row.task in {x.get("id") for x in (r.get("result") or {}).get("landed") or []} for r in runs)
    row.landed_by = ("workflow" if landed else "hand") if runs else None
    row.warn = disagreement(row)


def run_numbers(row: Row) -> tuple[bool, int, int] | None:
    if not row.attempts:
        return None
    return row.attempts[0] == "landed", row.attempts.count("review"), row.attempts.count("harness")


def git_numbers(row: Row) -> tuple[bool, int] | None:
    return None if row.commits is None else (row.commits == 1, row.commits - 1)


def disagreement(row: Row) -> str | None:
    runs, proxy = run_numbers(row), git_numbers(row)
    if runs is None or proxy is None or runs[:2] == proxy:
        return None
    return (f"WARN {row.task}: runs say first_pass={runs[0]} rework={runs[1]}, "
            f"git says first_pass={proxy[0]} rework={proxy[1]}")


def fmt_bool(value: bool) -> str:
    return "yes" if value else "no"


def pass_cells(row: Row, with_runs: bool) -> list[str]:
    runs = run_numbers(row) if with_runs else None
    if runs:
        return [fmt_bool(runs[0]), str(runs[1]), str(runs[2])]
    proxy = git_numbers(row)
    if proxy is None:
        return ["-", "-", "-"]
    tag = " (git)" if with_runs else ""
    return [fmt_bool(proxy[0]) + tag, str(proxy[1]) + tag, "-"]


def fidelity_cells(row: Row) -> list[str]:
    if row.commits is None:
        return ["-", "-", "-", "-"]
    both, union = row.named & row.touched, row.named | row.touched
    ratio = f"{len(both) / len(union):.2f}" if union else "-"
    return [str(len(both)), str(len(row.touched - row.named)), str(len(row.named - row.touched)), ratio]


def header(with_runs: bool) -> list[str]:
    src = "" if with_runs else " (git)"
    return ["task", "archive", "record", f"first_pass{src}", f"rework{src}", "harness",
            "landed_by", "named∩touched", "unplanned", "not_done", "fidelity", "range"]


def cells(row: Row, with_runs: bool) -> list[str]:
    head = [row.task, row.archive.sha[:7]]
    if not row.record:
        return head + ["none"] + ["-"] * 9
    rng = f"{row.range_first[:7]}^..{row.archive.sha[:7]}^" if row.range_first else "undefined"
    return (head + [f"verifyExit {row.record['verifyExit']}"] + pass_cells(row, with_runs)
            + [row.landed_by or "-"] + fidelity_cells(row) + [rng])


def render_text(rows: list[Row], with_runs: bool) -> str:
    lines = ["\t".join(header(with_runs))] + ["\t".join(cells(r, with_runs)) for r in rows]
    return "\n".join(lines + [r.warn for r in rows if r.warn]) + "\n"


def md_row(values: list[str]) -> str:
    return "| " + " | ".join(v.replace("|", "\\|") for v in values) + " |"


def render_sets(rows: list[Row]) -> list[str]:
    out = []
    for r in rows:
        if r.record and r.commits is not None and (r.touched - r.named or r.named - r.touched):
            out.append(f"- **{r.task}** unplanned: {', '.join(sorted(r.touched - r.named)) or '-'}; "
                       f"not_done: {', '.join(sorted(r.named - r.touched)) or '-'}")
    return out or ["- none: every recorded range touched exactly the files its brief named"]


def render_markdown(rows: list[Row], with_runs: bool, argv: list[str], today: str) -> str:
    recorded = [r for r in rows if r.record]
    unrecorded = [f"- {r.task} — `{r.archive.sha[:7]}` {r.archive.subject}" for r in rows if not r.record]
    lines = [
        "# SDLC measurements — ship-dev-plan LAND records", "",
        f"MEASURED {today}", "",
        "```", "python3 bin/sdlc_measurements.py " + shlex.join(argv), "```", "",
        md_row(header(with_runs)), md_row(["---"] * len(header(with_runs))),
        *[md_row(cells(r, with_runs)) for r in recorded], "",
        *[f"- {r.warn}" for r in recorded if r.warn],
        "## Plan fidelity — the sets", "", *render_sets(recorded), "",
        "## How to read it", "",
        "- `first_pass`, `rework`, `harness` come from the run records (one `land:<id>` attempt each);",
        "  a `(git)` cell is the proxy: commits between the brief's first commit and its archive.",
        "  `harness` is an attempt the harness lost (null return, errored agent, a land that did not",
        "  land), never counted as rework.",
        "- `fidelity` is file-set overlap, |named ∩ touched| / |named ∪ touched|. It saturates: a",
        "  deviation lands as `fix(` commits inside files the brief already named, so it shows in",
        "  `rework`, not here. That is the finding, not a defect of the number.",
        "- `range: undefined` means the brief was added more than once or in a batch commit with",
        "  other briefs, so no range belongs to it alone.", "",
        "## No LAND record", "", *(unrecorded or ["- none"]), "",
        "## Not derivable without new instrumentation", "",
        "- Who approved: no reviewer identity is recorded anywhere in a LAND record.",
        "- Review effort actually used and time-in-review: only the requested effort",
        "  (`TASKS[id].review`) exists.",
    ]
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", required=True, help="the repository to read")
    p.add_argument("--since", help="only archive commits since this date (git --since)")
    p.add_argument("--runs", help="glob of Workflow run records (wf_*.json)")
    p.add_argument("--markdown", action="store_true", help="print the markdown document")
    p.add_argument("--today", help="the MEASURED date in --markdown output (required with it)")
    args = p.parse_args(argv)
    if args.markdown and not args.today:
        p.error("--markdown needs --today: the document reads no clock")
    return args


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    runs = load_runs(args.runs)
    rows = measure(args.repo, args.since, runs)
    with_runs = args.runs is not None
    out = render_markdown(rows, with_runs, argv, args.today) if args.markdown else render_text(rows, with_runs)
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
