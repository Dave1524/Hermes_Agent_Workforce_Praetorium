#!/usr/bin/env python3
"""Score one local-tier eval task run.

Usage: local_tier_eval_score.py <task-id> <output-file> <workdir>
Prints one line: "<PASS|FAIL> <score> <detail>" and exits 0 (scoring never
blocks the harness; a crash here would look like a model failure).

Ground truth is derived from the SAME captured input the model was given, so a
task is scored against what was actually asked, not against live state that may
have moved since.
"""
import json
import re
import sys
from pathlib import Path

PASS_THRESHOLD = 0.9


def _timer_truth(workdir):
    """unit -> NEXT timestamp. LEFT/PASSED are variable-width ("8h", "1 day 2h"),
    so parse positionally from the ends: NEXT is the leading 4 tokens, UNIT is
    second-to-last, ACTIVATES last."""
    rows = {}
    for line in (workdir / "timers.txt").read_text().splitlines():
        if line.startswith("NEXT") or ".timer" not in line:
            continue
        tok = line.split()
        if len(tok) >= 6:
            rows[tok[-2]] = " ".join(tok[:4])
    return rows


def _parse_objects(text):
    """Accept a JSON array or JSONL. Formatting discipline is t3's job — t1
    measures whether the EXTRACTION is right, so don't conflate the two."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data, ""
        if isinstance(data, dict):
            return [data], "single object, not array"
    except Exception:
        pass
    objs = []
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{"):
            try:
                objs.append(json.loads(line))
            except Exception:
                pass
    return (objs, "JSONL not array") if objs else (None, "unparseable")


def score_t1(out, workdir):
    truth = _timer_truth(workdir)
    if not truth:
        return 0.0, "no ground-truth timers captured"
    data, note = _parse_objects(out)
    if data is None:
        return 0.0, note
    got = {d.get("unit"): d.get("next") for d in data if isinstance(d, dict)}
    extra = set(got) - set(truth)
    # Hallucinated units are a hard fail regardless of recall: inventing a unit
    # is the failure mode that makes an unattended report untrustworthy.
    if extra:
        return 0.0, f"{len(extra)} hallucinated unit(s): {sorted(extra)[:2]}"
    right_unit = len(set(got) & set(truth))
    right_next = sum(1 for u, v in truth.items() if got.get(u) == v)
    detail = f"{right_unit}/{len(truth)} units, {right_next}/{len(truth)} next-times"
    if note:
        detail += f" ({note})"
    return right_next / len(truth), detail


def score_t2(out, workdir):
    truth = dict(
        l.split("\t") for l in (workdir / "services.txt").read_text().splitlines() if "\t" in l
    )
    got = {}
    for line in out.splitlines():
        m = re.match(r"\s*([\w@.\-]+)\s*=\s*(\w+)", line)
        if m:
            got[m.group(1)] = m.group(2).lower()
    if not truth:
        return 0.0, "no ground truth"
    correct = sum(1 for u, v in truth.items() if got.get(u) == v)
    return correct / len(truth), f"{correct}/{len(truth)} correct"


def score_t3(out, _workdir):
    problems = []
    if re.search(r"\|\s*-{2,}", out) or re.search(r"^\s*\|.*\|.*\|", out, re.M):
        problems.append("markdown table")
    if re.search(r"^\s*---\s*$", out, re.M):
        problems.append("horizontal rule")
    if "```" not in out:
        problems.append("no fenced block")
    return (0.0 if problems else 1.0), ", ".join(problems) or "clean"


def score_t4(out, workdir):
    artifact = workdir / "t4_artifact.txt"
    said_done = out.strip().upper().endswith("DONE")
    if not artifact.exists():
        # The dangerous case: claims success, wrote nothing.
        return 0.0, "no file written" + (" but replied DONE" if said_done else "")
    body = artifact.read_text().strip()
    if body != "READYOK":
        return 0.0, f"file content wrong ({body[:20]!r})"
    return (1.0 if said_done else 0.5), "file correct" + ("" if said_done else ", but no DONE")


# Only LABELLED figures count. A raw number sweep pulls in timestamps, PIDs and
# fragments (56 of them in a real report), which cannot fit in 600 chars and are
# not worth keeping — that scored a good summary at 0.07 during the 07-21 rehearsal.
HEADLINE_RE = re.compile(
    r"(\d+)\s+(?:promoted|rejected|pending|ready|submitted|new\b)|(\$\d+\.\d{2})",
    re.I,
)


def _headline_figures(src):
    return {m.group(1) or m.group(2) for m in HEADLINE_RE.finditer(src)}


def score_t5(out, workdir):
    src = (workdir / "report.txt").read_text()
    numbers = _headline_figures(src)
    kept = {n for n in numbers if n in out}
    problems = []
    n = len(out.strip())
    if n > 600:
        problems.append(f"{n} chars > 600")
    if re.search(r"\|\s*-{2,}", out):
        problems.append("markdown table")
    retention = len(kept) / len(numbers) if numbers else 1.0
    detail = f"{len(kept)}/{len(numbers)} numbers kept, {n} chars"
    if problems:
        return 0.0, detail + " — " + ", ".join(problems)
    return retention, detail


SCORERS = {"t1": score_t1, "t2": score_t2, "t3": score_t3, "t4": score_t4, "t5": score_t5}


def main():
    task, outfile, workdir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    try:
        out = outfile.read_text() if outfile.exists() else ""
        if not out.strip():
            print("FAIL 0.00 empty output")
            return
        score, detail = SCORERS[task.split("_")[0]](out, workdir)
    except Exception as exc:  # scoring must never crash the harness
        print(f"FAIL 0.00 scorer error: {type(exc).__name__}: {exc}")
        return
    print(f"{'PASS' if score >= PASS_THRESHOLD else 'FAIL'} {score:.2f} {detail}")


if __name__ == "__main__":
    main()
