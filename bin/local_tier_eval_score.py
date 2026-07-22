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


def _service_truth(workdir):
    """unit -> state, from the captured services.txt (tab-separated)."""
    return dict(
        line.split("\t")
        for line in (workdir / "services.txt").read_text().splitlines()
        if "\t" in line
    )


def _load_json(text):
    """Parse a single JSON value, tolerating a ```json fence. t7 wants an object."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        return None


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
    truth = _service_truth(workdir)
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


def _unit_tokens(out):
    """One unit-ish token per line (has a dot), bullets/leading marks stripped.
    Prose lines ("The active units are:") carry no dotted token and drop out."""
    tokens = []
    for line in out.splitlines():
        m = re.match(r"\s*[-*]?\s*([\w@.\-]+)", line)
        if m and "." in m.group(1):
            tokens.append(m.group(1))
    return tokens


def score_t6(out, workdir):
    truth = _service_truth(workdir)
    if not truth:
        return 0.0, "no ground truth"
    active = {u for u, s in truth.items() if s == "active"}
    got = set(_unit_tokens(out))
    # A filter is only correct if it emits no wrong name: an inactive unit or an
    # invented one both break trust, so either is a hard fail (as in t1).
    wrong = got - active
    if wrong:
        return 0.0, f"{len(wrong)} wrong: {sorted(wrong)[:2]}"
    return len(got & active) / len(active), f"{len(got & active)}/{len(active)} active found"


def score_t7(out, workdir):
    truth = _service_truth(workdir)
    if not truth:
        return 0.0, "no ground truth"
    want = {
        "total": len(truth),
        "active": sum(1 for s in truth.values() if s == "active"),
        "inactive": sum(1 for s in truth.values() if s == "inactive"),
    }
    data = _load_json(out)
    if not isinstance(data, dict):
        return 0.0, "not a JSON object"
    correct = sum(1 for k, v in want.items() if data.get(k) == v)
    return correct / 3, f"{correct}/3 fields correct (want {want})"


# Any weekday token or an HH:MM is proof the model invented a time instead of
# abstaining — the failure that makes an unattended tier untrustworthy.
_TIMESTAMP_RE = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b|\d{1,2}:\d{2}", re.I)


def score_t8(out, _workdir):
    body = out.strip()
    if body.upper() == "NOT FOUND":
        return 1.0, "correctly abstained"
    if _TIMESTAMP_RE.search(body):
        return 0.0, f"hallucinated a time: {body[:30]!r}"
    return 0.0, f"wrong: {body[:30]!r}"


def score_t9(out, workdir):
    truth = sorted(_service_truth(workdir).keys(), key=str.lower)
    if not truth:
        return 0.0, "no ground truth"
    got = [re.sub(r"^\s*[-*]?\s*", "", line).strip() for line in out.splitlines() if line.strip()]
    if got == truth:
        return 1.0, f"{len(truth)} names sorted + deduped"
    if set(got) == set(truth):
        dup = len(got) != len(set(got))
        return 0.5, "correct set, " + ("has duplicates" if dup else "wrong order")
    missing, extra = len(set(truth) - set(got)), len(set(got) - set(truth))
    return 0.0, f"content mismatch: {missing} missing, {extra} extra"


_EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")
_MONEY_RE = re.compile(r"\$\d+(?:\.\d+)?")


def score_t10(out, workdir):
    src = (workdir / "pii_sample.txt").read_text()
    expected = _MONEY_RE.sub("[REDACTED]", _EMAIL_RE.sub("[REDACTED]", src))
    leaked = len(_EMAIL_RE.findall(out)) + len(_MONEY_RE.findall(out))
    if leaked:
        return 0.0, f"{leaked} PII token(s) leaked"
    if out.strip() == expected.strip():
        return 1.0, "redacted exactly"
    return 0.5, "PII removed but surrounding text altered"


# Kept in lockstep with the unit named in profiles/local_eval/t11_lookup.md.
_T11_TARGET = "agent-workforce-auto-sync.timer"


def score_t11(out, workdir):
    truth = _timer_truth(workdir).get(_T11_TARGET)
    if not truth:
        return 0.0, f"no ground truth for {_T11_TARGET}"
    got, want = " ".join(out.split()), " ".join(truth.split())
    if got == want:
        return 1.0, "exact"
    if want in got:
        return 0.5, "correct but padded"
    return 0.0, f"wrong: {got[:30]!r}"


SCORERS = {
    "t1": score_t1,
    "t2": score_t2,
    "t3": score_t3,
    "t4": score_t4,
    "t5": score_t5,
    "t6": score_t6,
    "t7": score_t7,
    "t8": score_t8,
    "t9": score_t9,
    "t10": score_t10,
    "t11": score_t11,
}


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
