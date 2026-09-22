#!/usr/bin/env python3
"""Score `claude plugin eval` results against a recorded baseline, and say what moved.

usage: agent_config_eval_compare.py <result.json>... --baseline <path> [--record]
                                    [--tolerance F]

WHY A COMPARATOR AND NOT --threshold. `claude plugin eval` can fail a run below an absolute
score, and an absolute pass mark on model behaviour is the thing bin/fleet_eval.sh:13-20
argues against at length: it goes red for reasons nobody chose — a model rollout, a harness
change — and a suite that goes red for reasons nobody chose is muted within a week. So the
runner passes --threshold 0 and the verdict is made here, against the score measured when the
case was added.

FOUR VERDICTS ON A CASE THAT ASKS WHETHER A SKILL FIRES, AND TWO OF THEM ARE THE
INTERESTING ONES:

  REGRESSION   score fell below the baseline by more than the tolerance.  red
  IMPROVED     score rose above it by more than the tolerance.            reported, not red,
               and the baseline is LEFT ALONE — re-recording is a deliberate commit.
  MISSING      the baseline names a case this run did not produce.        red
  UNBASELINED  this run produced a case the baseline does not name.       red

MISSING AND UNBASELINED ARE WHY THIS IS A JOIN AND NOT A LOOKUP. A case deleted from the tree
and a case that never ran both read as "no bad news" to a one-directional check, and an
unbaselined case is a pass mark nobody ever measured — the exact shape of a gate that is
green because it is asserting nothing. Both are red here, in both directions.

MISSING IS SCOPED TO THE OWNERS PRESENT IN THE RESULTS. `--owner claudius` is a legitimate
partial run; every other owner's cases are not missing, they were not asked for. Scoping by
owner is what lets a partial run be honest instead of noisy.

A CASE NAMED `…-must-not-fire` IS A CEILING, AND THE VERDICT FLIPS. Every verdict above
reads a fall as the bad news, which is right for a case asking "does the skill still fire"
and exactly backwards for one asking "does it stay out of the way". A negative case
baselines at 0.000, so under the floor rule a run where the skill fired every time would
score 1.000 and be reported as IMPROVED — the failure it exists to catch, printed as good
news. The direction is carried by the case NAME rather than a field in the baseline
because --record rewrites that file wholesale from the measured scores: a field would be
dropped on the first re-record and the case would silently become a floor again, which is
the same fail-open shape as reading the owner off the case list. The name survives, because
it is the key.

  OVERFIRED     a ceiling case rose above its recorded score.               red
  QUIETER       a ceiling case fell below it.                               reported

`gate: false` ON A BASELINE ENTRY MAKES A CASE REPORT-ONLY, AND IT IS NOT A MUTE BUTTON. Some
skills fire reproducibly and some do not, and at runs=3 the difference is not a matter of
opinion: measured three times over on 2026-09-22, nine of the thirteen `-fires` cases scored
1.000 every run and three swung by a third or more between identical runs of an unchanged
tree — one of them 1.000, 1.000, 0.333, which the floor rule correctly called a REGRESSION and
which was noise. A suite that goes red for reasons nobody chose is muted within a week, and
the honest alternative to muting the whole thing is to say per case which ones carry a
verdict. A `gate: false` case is still measured, still printed with its score and its
movement, and still delivered in the scorecard; it simply cannot fail the run. Raising `runs`
until those cases are stable is the other answer and costs about four times as much per run —
this one is reversible by deleting a line.

THE TOLERANCE IS 1/runs, AND THE EPSILON UNDER IT IS NOT DECORATION. At runs=3 a score is
quantised to 0, 1/3, 2/3 or 1, so one flaky run of three IS a 1/3 drop and the tolerance
exists to absorb exactly one. But 2/3 computes as 0.6666666666666666 while 1 - 1/3 computes
as 0.6666666666666667, so the bare comparison makes one flaky run red — the tolerance would
absorb nothing at precisely the value it was sized for. Every comparison is therefore
slackened by EPS. If the weekly run is noisy, raise `runs`; never raise the tolerance.
"""
import argparse
import datetime
import json
import pathlib
import sys

EPS = 1e-9
CEILING_SUFFIX = "-must-not-fire"


def read_result(path):
    """(owner, [(case, score, runs)], claude_version, model) for one result file.

    THE OWNER COMES FROM THE PLUGIN, NEVER FROM THE CASES. A run that produced no cases at
    all still names its plugin, and that is the run whose baselined cases are MISSING — read
    the owner off the case list instead and a zero-case result contributes no owner, so the
    scope test below skips every MISSING row and the comparator exits 0 on the one input it
    exists to catch. Measured on the fixtures, 2026-09-22: it failed open.

    The plugin name also survives the copy. The runner evaluates a COPY under a temp path and
    --self-check's copy is not named after its owner, so the directory cannot be trusted for
    this and the manifest's `praetorium-<owner>` can.
    """
    data = json.loads(pathlib.Path(path).read_text())
    suite = data.get("suite") or {}
    plugins = suite.get("plugins") or []
    name = plugins[0].get("name", "") if plugins else ""
    owner = name[len("praetorium-"):] if name.startswith("praetorium-") else name
    if not owner:
        owner = pathlib.Path(suite.get("root", "unknown")).name
    cases = []
    for case in data.get("cases", []):
        arms = (case.get("arms") or {}).get("with") or []
        cases.append((
            case.get("name", "?"),
            float((case.get("aggregates") or {}).get("score", 0.0)),
            len(arms) or int(case.get("runsPerCase") or 0),
        ))
    return owner, cases, data.get("claudeVersion", ""), suite.get("modelOverride", "")


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("results", nargs="+")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--record", action="store_true",
                    help="the ONLY writer of the baseline file")
    ap.add_argument("--tolerance", type=float, default=None)
    args = ap.parse_args()

    measured, owners, versions, models, runs_seen = {}, set(), set(), set(), set()
    for path in args.results:
        try:
            owner, cases, version, model = read_result(path)
        except (OSError, ValueError, KeyError) as exc:
            print(f"results/{pathlib.Path(path).name}|FAIL||unreadable result: {exc}")
            return 1
        owners.add(owner)
        if version:
            versions.add(version)
        if model:
            models.add(model)
        for case, score, runs in cases:
            measured[f"{owner}/{case}"] = score
            runs_seen.add(runs)

    runs = max(runs_seen) if runs_seen else 3
    tolerance = args.tolerance if args.tolerance is not None else (1.0 / runs if runs else 0.0)

    if args.record:
        # SCORES ARE REMEASURED; A `notes` A HUMAN WROTE IS CARRIED FORWARD. --record rewrites
        # this file wholesale, which is right for everything it measures and wrong for the one
        # thing it cannot: the sentence saying why a case is baselined where it is. A case
        # whose recorded score is inside the tolerance of the floor can never go red again
        # (at runs=3, anything at or below 0.333), and tests/test_agent_config_eval.sh makes
        # that state legal only when a `notes` declares it — so dropping the note here would
        # turn every re-record into a red the re-recorder then "fixes" by rewriting the note
        # from memory, or worse, deleting the case.
        previous = {}
        try:
            previous = (json.loads(pathlib.Path(args.baseline).read_text()).get("cases") or {})
        except (OSError, ValueError):
            pass

        def annotations(key):
            kept = {}
            for field in ("gate", "notes"):
                if field in (previous.get(key) or {}):
                    kept[field] = previous[key][field]
            return kept
        baseline = {
            "_comment": (
                "Recorded by bin/agent_config_eval.sh --record. A score here is the measured "
                "behaviour when the case was added, not a target: bin/agent_config_eval_compare.py "
                "reports a fall below it and leaves a rise alone — or the reverse, for a case "
                "named `…-must-not-fire`. Re-record only as a deliberate commit that says why."
            ),
            "measured": datetime.date.today().isoformat(),
            "claude": sorted(versions)[0] if versions else "",
            "model": sorted(models)[0] if models else "",
            "runs": runs,
            # NOT round(…, 6). 1/3 rounded to 0.333333 leaves `base - tolerance` at 3.3e-7
            # instead of 0.0, which is 333x the epsilon below — so a case baselined at 1/3 and
            # measured at 0.000, exactly the one flaky run the tolerance is sized to absorb,
            # came back REGRESSION. Measured live 2026-09-22 on
            # claudius/investment-research-fires. The prettier number defeated the guard the
            # docstring above spends a paragraph on.
            "tolerance": tolerance,
            "cases": {k: {"score": v, **annotations(k)} for k, v in sorted(measured.items())},
        }
        pathlib.Path(args.baseline).write_text(json.dumps(baseline, indent=2) + "\n")
        # A --record run that printed only "recorded N cases" would hide the scores it just
        # froze into the pass mark, which is the one moment they are worth reading.
        for key, score in sorted(measured.items()):
            print(f"case/{key}|PASS|{score:.3f}|recorded")
        print(f"baseline|PASS|{len(measured)}|recorded {args.baseline} "
              f"(measured {baseline['measured']}, model {baseline['model']}, runs {runs})")
        return 0

    try:
        baseline = json.loads(pathlib.Path(args.baseline).read_text())
    except (OSError, ValueError) as exc:
        print(f"baseline|FAIL||unreadable baseline {args.baseline}: {exc}")
        return 1

    base_cases = baseline.get("cases") or {}
    if baseline.get("tolerance") is not None and args.tolerance is None:
        tolerance = float(baseline["tolerance"])

    failed = False
    for key in sorted(set(measured) | set(base_cases)):
        owner = key.split("/", 1)[0]
        score = measured.get(key)
        base = (base_cases.get(key) or {}).get("score")

        if base is None:
            failed = True
            print(f"case/{key}|FAIL|{score:.3f}|UNBASELINED — no recorded score to compare "
                  f"against; measure it with --record before it lands")
            continue
        if score is None:
            if owner not in owners:
                continue
            failed = True
            print(f"case/{key}|FAIL||MISSING — baselined at {base:.3f} and this run of "
                  f"{owner} produced no such case")
            continue

        base = float(base)
        rose = score > base + tolerance + EPS
        fell = score + EPS < base - tolerance
        if (base_cases[key] or {}).get("gate") is False:
            moved = "moved" if rose or fell else "steady"
            print(f"case/{key}|PASS|{score:.3f}|REPORTED, not gated — {moved} against "
                  f"{base:.3f}; see the baseline's notes")
            continue
        if key.endswith(CEILING_SUFFIX):
            if rose:
                failed = True
                print(f"case/{key}|FAIL|{score:.3f}|OVERFIRED — a ceiling case, was "
                      f"{base:.3f}, tolerance {tolerance:.3f}")
            elif fell:
                print(f"case/{key}|PASS|{score:.3f}|QUIETER — ceiling was {base:.3f}; "
                      f"baseline left alone, re-record deliberately")
            else:
                print(f"case/{key}|PASS|{score:.3f}|ceiling {base:.3f} ± {tolerance:.3f}")
            continue
        if fell:
            failed = True
            print(f"case/{key}|FAIL|{score:.3f}|REGRESSION — was {base:.3f}, "
                  f"tolerance {tolerance:.3f}")
        elif rose:
            print(f"case/{key}|PASS|{score:.3f}|IMPROVED — was {base:.3f}; baseline left "
                  f"alone, re-record deliberately")
        else:
            print(f"case/{key}|PASS|{score:.3f}|baseline {base:.3f} ± {tolerance:.3f}")

    print(f"baseline/measured|PASS|{baseline.get('measured', '?')}|"
          f"model {baseline.get('model', '?')}, claude {baseline.get('claude', '?')}, "
          f"runs {baseline.get('runs', '?')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
