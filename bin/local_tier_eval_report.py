#!/usr/bin/env python3
"""Render the local-tier eval scorecard from results.psv.

Usage: local_tier_eval_report.py <workdir>   (scorecard to stdout)

Deliberately reports the determinism of the three t1 runs separately from their
accuracy: a model can be perfectly stable and stably wrong, and the two failures
have different remedies.
"""
import sys
from collections import defaultdict
from pathlib import Path

TASK_LABEL = {
    "t1": "extraction (JSON, no hallucinated units)",
    "t2": "classification (service state)",
    "t3": "format compliance (no tables)",
    "t4": "artifact discipline (writes the file)",
    "t5": "summarise (<=600 chars, keeps numbers)",
}


def main():
    work = Path(sys.argv[1])
    rows = []
    for line in (work / "results.psv").read_text().splitlines():
        task, model, verdict, secs = line.split("|")
        status, score, detail = verdict.split(" ", 2)
        rows.append((task, model, status, float(score), detail, secs))

    by_model = defaultdict(list)
    for r in rows:
        by_model[r[1]].append(r)

    print(f"# Local-tier eval — {work.name}\n")
    for model, rs in by_model.items():
        passed = sum(1 for r in rs if r[2] == "PASS")
        print(f"## {model} — {passed}/{len(rs)} passed\n")
        print("```")
        print(f"{'task':<9} {'result':<6} {'score':<6} {'time':<7} detail")
        for task, _m, status, score, detail, secs in rs:
            print(f"{task:<9} {status:<6} {score:<6.2f} {secs:<7} {detail}")
        print("```")

        t1 = [r for r in rs if r[0].startswith("t1")]
        if len(t1) > 1:
            outs = [(work / f"{r[0]}__{model}.out").read_text() for r in t1]
            stable = len(set(outs)) == 1
            print(
                f"\n- **Determinism (t1 x{len(t1)}):** "
                f"{'identical' if stable else f'{len(set(outs))} DIFFERENT outputs'}"
                f" — temperature 0 {'holds' if stable else 'is NOT holding'}\n"
            )
        for task_key, label in TASK_LABEL.items():
            hits = [r for r in rs if r[0].startswith(task_key)]
            if hits and all(h[2] == "FAIL" for h in hits):
                print(f"- FAILED: {label}")
        print()


if __name__ == "__main__":
    main()
