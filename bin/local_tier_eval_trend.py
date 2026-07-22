#!/usr/bin/env python3
"""Longitudinal pass-rate for the local-tier eval, read from history.psv.

Usage: local_tier_eval_trend.py <history.psv> [last_n_runs]

Answers the question the single-run scorecard cannot: is the local model reliable
OVER TIME and across the day, or does it pass at 03:00 and fail at 14:00? Groups
by task base (t1_run1..t1_run3 collapse to t1) over the most recent N runs.
"""
import sys
from collections import defaultdict
from pathlib import Path


def _load(hist):
    rows = []
    for line in hist.read_text().splitlines():
        if line.startswith("run_ts|"):
            continue
        parts = line.split("|")
        if len(parts) == 6:
            rows.append(parts)  # run_ts, task, model, status, score, secs
    return rows


def _task_sort_key(task):
    """t1..t11 in numeric order, not lexical (so t10 follows t9, not t1)."""
    return (len(task), task)


def main():
    hist = Path(sys.argv[1])
    last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    if not hist.exists():
        print("no history yet")
        return
    rows = _load(hist)
    if not rows:
        print("no history yet")
        return

    runs = sorted({r[0] for r in rows})
    recent = set(runs[-last_n:])
    rows = [r for r in rows if r[0] in recent]

    by_task = defaultdict(list)
    per_run = defaultdict(lambda: [0, 0])
    for run_ts, task, _model, status, _score, _secs in rows:
        ok = status == "PASS"
        by_task[task.split("_")[0]].append(ok)
        per_run[run_ts][1] += 1
        per_run[run_ts][0] += int(ok)

    print(f"# Local-tier trend — last {len(recent)} run(s), newest {runs[-1]}\n")
    print("```")
    print(f"{'task':<6} {'pass-rate':<11} n")
    for task in sorted(by_task, key=_task_sort_key):
        res = by_task[task]
        print(f"{task:<6} {sum(res) / len(res) * 100:>4.0f}%       {sum(res)}/{len(res)}")
    print("```")

    line = "  ".join(f"{p}/{t}" for _ts, (p, t) in sorted(per_run.items()))
    print(f"\nper-run passed/total (oldest -> newest):\n  {line}")


if __name__ == "__main__":
    main()
