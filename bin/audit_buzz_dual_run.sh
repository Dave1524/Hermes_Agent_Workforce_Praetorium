#!/usr/bin/env bash
# audit_buzz_dual_run.sh — the only evidence that may close the Discord cutover.
#
# usage: audit_buzz_dual_run.sh [--days N] [--receipts FILE] [--unit UNIT] [--verbose]
#
# For every expected timer fire in the window it answers one question: did Discord, the
# Buzz channel AND the Pulse note all land, or did this producer correctly have nothing
# to say? Anything else is a gap and exits non-zero.
#
# Why receipts and not the journal: the two live failures this migration exists to fix
# both stayed green. A unit that exits 0 having delivered nothing, and one that delivered
# a 26-hour-old file, are indistinguishable from `systemctl status`. Only a per-invocation
# receipt records what actually reached a surface.
#
# The window ends YESTERDAY. Today's fires may not have happened yet — auditing them
# would manufacture a gap every morning and train the reader to ignore the output.
#
# READ-ONLY: this script opens the receipt file, the producer manifest and the timer
# sources, and writes nothing anywhere.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$BIN_DIR/.." && pwd)"
MANIFEST="${BUZZ_PRODUCERS:-$BIN_DIR/buzz_producers.tsv}"
TIMER_DIR="${BUZZ_TIMER_DIR:-$REPO_ROOT/systemd}"
RECEIPTS="${DELIVERY_RECEIPTS:-$HOME/logs/delivery-receipts.jsonl}"
DAYS=7
ONLY_UNIT=""
VERBOSE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --days)     DAYS="${2:-7}"; shift 2 ;;
    --receipts) RECEIPTS="${2:-}"; shift 2 ;;
    --unit)     ONLY_UNIT="${2:-}"; shift 2 ;;
    --verbose)  VERBOSE=1; shift ;;
    -h|--help)  sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "audit: unrecognized argument: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$RECEIPTS" ]; then
  echo "audit: no receipt file at $RECEIPTS — nothing can be certified" >&2
  exit 1
fi

# The manifest carries route/payload/status/silence; the calendar is read from each
# unit's own timer so the two can never drift. Everything downstream is one python pass
# over the receipts, because the matching is per (unit, day) and date arithmetic in
# shell is where this kind of report grows its own bugs.
python3 - "$MANIFEST" "$TIMER_DIR" "$RECEIPTS" "$DAYS" "$ONLY_UNIT" "$VERBOSE" <<'PY'
import datetime
import json
import os
import re
import sys

manifest_path, timer_dir, receipts_path, days, only_unit, verbose = sys.argv[1:7]
days = int(days)
verbose = verbose == "1"

DAY_NAMES = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_manifest():
    rows = []
    for line in open(manifest_path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        unit, route, payload, status, silence = line.rstrip("\n").split("\t")
        rows.append(dict(unit=unit, route=route, payload=payload,
                         status=status, silence=silence))
    return rows


def calendars(unit):
    """OnCalendar lines for a unit's sibling timer, or [] when it is on-demand."""
    stem = unit[:-len(".service")] if unit.endswith(".service") else unit
    path = os.path.join(timer_dir, stem + ".timer")
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("OnCalendar="):
            out.append(line.split("=", 1)[1].strip())
    return out


def weekdays_for(spec):
    """The weekday numbers a single OnCalendar expression fires on.

    None means "not a per-day schedule" — a polling spec like `*:0/15` fires many
    times a day and carries no expectation that any given day produced output.
    """
    head = spec.split()[0]
    if head.startswith("*:") or re.fullmatch(r"[\d,/*:]+", head):
        return None            # a time-only spec: polls, no daily expectation
    if head.startswith("*-*-*"):
        return set(range(7))   # every day
    wanted = set()
    for part in head.split(","):
        if ".." in part:
            lo, hi = part.split("..")
            if lo not in DAY_NAMES or hi not in DAY_NAMES:
                return None
            i, j = ORDER.index(lo), ORDER.index(hi)
            span = ORDER[i:j + 1] if i <= j else ORDER[i:] + ORDER[:j + 1]
            wanted.update(DAY_NAMES[d] for d in span)
        elif part in DAY_NAMES:
            wanted.add(DAY_NAMES[part])
        else:
            return None
    return wanted or None


def expected_days(unit, window):
    specs = calendars(unit)
    if not specs:
        return []              # on-demand (agent-alert@): no expected fires
    wanted = set()
    for spec in specs:
        got = weekdays_for(spec)
        if got is None:
            return []          # polling schedule: audited on what it did send
        wanted |= got
    return [d for d in window if d.weekday() in wanted]


def load_receipts():
    by_unit_day = {}
    with open(receipts_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            job, ts = row.get("job", ""), row.get("ts", "")
            if not job or len(ts) < 10:
                continue
            by_unit_day.setdefault((job, ts[:10]), []).append(row)
    return by_unit_day


def verdict(rows):
    """Worst verdict among the receipts a unit wrote on one day."""
    ranked = []
    for row in rows:
        legs = [row.get("discord_result"), row.get("buzz_result"), row.get("pulse_result")]
        outcome = row.get("outcome", "")
        if outcome == "skipped":
            ranked.append((3, "SKIPPED", row.get("error") or "nothing was sent"))
        elif outcome == "failed":
            ranked.append((4, "FAILED", row.get("error") or "all surfaces failed"))
        elif all(leg == "ok" for leg in legs):
            ranked.append((0, "ok", ""))
        else:
            bad = [name for name, leg in zip(("discord", "buzz", "pulse"), legs) if leg != "ok"]
            ranked.append((2, "PARTIAL", "not delivered: " + ", ".join(bad)))
    ranked.sort(reverse=True)
    return ranked[0][1], ranked[0][2]


today = datetime.datetime.now(datetime.timezone.utc).date()
window = [today - datetime.timedelta(days=i) for i in range(days, 0, -1)]
receipts = load_receipts()
rows = load_manifest()
if only_unit:
    rows = [r for r in rows if r["unit"] == only_unit]
    if not rows:
        print("audit: {} is not in the producer manifest".format(only_unit))
        sys.exit(2)

print("Buzz dual-run audit — {} day window, {} .. {}".format(
    days, window[0].isoformat(), window[-1].isoformat()))
print("receipts: {}".format(receipts_path))
print("")

gaps = 0
pending = []
for row in rows:
    unit = row["unit"]
    if row["status"] != "wired":
        pending.append(unit)
        continue

    lines = []
    n_ok = n_silent = 0
    fires = expected_days(unit, window)
    for day in fires:
        key = day.isoformat()
        # A template unit writes receipts under its instance name (agent-alert@foo.service).
        found = [r for (job, d), rs in receipts.items() if d == key
                 for r in rs
                 if job == unit or (unit.endswith("@.service")
                                    and job.startswith(unit[:-len(".service")]))]
        if not found:
            if row["silence"] == "allowed":
                n_silent += 1
                if verbose:
                    lines.append("    {}  silent (allowed)".format(key))
                continue
            lines.append("    {}  MISSING — no receipt for an expected fire".format(key))
            gaps += 1
            continue
        state, detail = verdict(found)
        if state == "ok":
            n_ok += 1
            if verbose:
                lines.append("    {}  ok".format(key))
            continue
        lines.append("    {}  {} — {}".format(key, state, detail))
        gaps += 1

    # On-demand and polling producers have no expected calendar; audit what they sent.
    if not fires:
        sent = [r for (job, d), rs in receipts.items()
                if window[0].isoformat() <= d <= window[-1].isoformat()
                for r in rs
                if job == unit or (unit.endswith("@.service")
                                   and job.startswith(unit[:-len(".service")]))]
        if not sent:
            lines.append("    no fires in window — silent (on demand)")
        else:
            state, detail = verdict(sent)
            if state == "ok":
                lines.append("    {} receipt(s), all delivered".format(len(sent)))
            else:
                lines.append("    {} receipt(s) — {} — {}".format(len(sent), state, detail))
                gaps += 1

    # State the delivered/silent split rather than a bare "clean". A producer licensed to
    # stay quiet all week and one that delivered every day both have zero gaps, and only
    # the split distinguishes "nothing to say" from "nothing arrived".
    head = "{}  [{}]".format(unit, row["route"])
    if fires:
        head += "  {}/{} expected fire(s) delivered".format(n_ok, len(fires))
        if n_silent:
            head += ", {} silent (allowed)".format(n_silent)
    print(head)
    for line in lines:
        print(line)

if pending:
    print("")
    print("pending — not yet ported to Buzz, still Discord-only:")
    for unit in pending:
        print("    {}".format(unit))

print("")
if gaps:
    print("RESULT: {} gap(s). The dual-run clock restarts.".format(gaps))
elif pending and not only_unit:
    print("RESULT: no gaps among wired producers, but {} producer(s) are still "
          "unported. A fleet-wide clean day requires all of them.".format(len(pending)))
else:
    print("RESULT: clean.")

sys.exit(1 if gaps or (pending and not only_unit) else 0)
PY
