#!/usr/bin/env python3
"""
Offline behaviour test for bin/bd_stall_radar_kernel.py. Driven from
tests/test_bd_stall_radar_kernel.sh so bin/verify.sh picks it up.

No network, no qmd: the decision rules are pure functions over a deal dict and the
priorities text, and that is what is pinned. The cases are the ones measured live on
2026-09-11 (88 pipeline rows) when the token matcher failed in both directions.
"""
import datetime as dt
import importlib.util
import json
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "kernel", ROOT / "bin" / "bd_stall_radar_kernel.py")
k = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(k)

TODAY = dt.date(2026, 9, 11)
failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


def deal(stage="Prospect", last_contact="2026-08-01", next_action=None):
    return {"client": "X", "stage": stage, "last_contact": last_contact,
            "days_formula": None, "next_action_date": next_action, "trigger": ""}


PRIORITIES = """
### The Cold Hub — UNPARKED 2026-08-31, contact this week
### Rhenus (Arnold van Asten) — went direct; connect sent, awaiting acceptance
- State: lunch landed (Rotterdam). MKB Rotterdam event; Broekman's Rotterdam terminal.
- the channel-shift discipline that retired DACHSER/Ramon Van Dilst on 2026-05-26
- [[../05_knowledge/the_coldhub_org_profile]] and **DP World** (Joost Heere)
- "Capacity without contracted volume is the real cold-storage risk" · Jan de Rijk lunch
"""
PHRASES = k.priority_phrases(PRIORITIES)

print("--- scope: only Prospect rows are candidates; never-contacted rows are in ---")
for stage, want in [("Prospect", True), ("Qualified", False), ("Proposal", False),
                    ("Active", False), ("On Hold", False), ("Closed", False)]:
    ok, why = k.is_candidate(deal(stage=stage), TODAY)
    check(f"Stage {stage} silent 41d -> candidate={want} ({why})", ok is want)
ok, why = k.is_candidate(deal(last_contact=None), TODAY)
check(f"never-contacted Prospect is a candidate ({why})", ok and why == "never contacted")
ok, why = k.is_candidate(deal(stage="Qualified", last_contact=None), TODAY)
check(f"never-contacted Qualified is not ({why})", not ok)
ok, why = k.is_candidate(deal(last_contact="2026-09-08"), TODAY)
check(f"3d silent is recent, not a stall ({why})", not ok)
ok, why = k.is_candidate(deal(last_contact="2026-09-03"), TODAY)
check(f"8d silent is a stall ({why})", ok)

print("--- suppression matches the whole normalised name, never a lone token ---")
cases = [
    ("Embassy Freight Rotterdam B.V.", None, "city token in unrelated prose is not a match"),
    ("The ColdHub", "the coldhub", "Notion 'ColdHub' folds onto the vault's 'Cold Hub'"),
    ("Rhenus Contract Logistics Tilburg", "rhenus", "generic+city dropped -> short form matches"),
    ("Rhenus Logistics (Peter van der Steen)", "rhenus", "parenthetical dropped"),
    ("DP World", "dp world", "two short tokens match as a phrase"),
    ("DACHSER Netherlands Food Logistics", "dachser",
     "short form is the bare brand; the matcher cannot read that the mention says 'retired'"),
    ("Broekman Logistics", "broekman", "short form of a name whose prose mention is bare"),
    ("Global Logistics Rotterdam", None, "all-generic name has no short form and no full match"),
    ("Cold Chain Services", None, "all-generic name is never matched on 'cold' alone"),
    ("RealCold", None, "whitespace folding must not match lowercase prose ('the real cold-storage risk')"),
    ("Jan de Rijk Logistics", "jan de rijk", "particles may stay lowercase inside a capitalised phrase"),
]
for client, want, why in cases:
    got = k.named_in_priorities(client, PHRASES)
    check(f"{client!r} -> {got!r} ({why})", got == want)
check("legal suffix stripped before folding",
      k.name_forms("NVO Transport BV")[0][0] == "nvotransport")
check("short form needs >= 6 chars (a bare first name cannot match)",
      all(f != "peter" for f, _ in k.name_forms("Peter Logistics")))

print("--- suppression reasons and ordering ---")
r = k.suppression({**deal(), "client": "The ColdHub"}, PHRASES, TODAY)
check(f"named -> {r!r}", r == "actively managed (named in priorities: 'the coldhub')")
r = k.suppression({**deal(next_action="2026-10-01"), "client": "Nobody"}, PHRASES, TODAY)
check(f"future next action -> {r!r}", r and r.startswith("scheduled"))
r = k.suppression({**deal(next_action="2026-09-01"), "client": "Nobody"}, PHRASES, TODAY)
check("past next action does not suppress", r is None)

stalls = [
    {"client": "B never", "stage": "Prospect", "last_contact": None, "days": None,
     "never": True, "aging": False, "next_action_date": None, "trigger": ""},
    {"client": "A never", "stage": "Prospect", "last_contact": None, "days": None,
     "never": True, "aging": False, "next_action_date": None, "trigger": ""},
    {"client": "old", "stage": "Prospect", "last_contact": "2026-05-01", "days": 133,
     "never": False, "aging": True, "next_action_date": None, "trigger": ""},
    {"client": "warm", "stage": "Prospect", "last_contact": "2026-08-20", "days": 22,
     "never": False, "aging": False, "next_action_date": None, "trigger": ""},
]
stalls.sort(key=lambda c: (c["never"], c["aging"], -(c["days"] or 0), c["client"].lower()))
check("order is warm, aging, then never-contacted by name",
      [s["client"] for s in stalls] == ["warm", "old", "A never", "B never"])
prop = k.build_proposal(stalls, TODAY, 88)
check("headline counts all three buckets",
      prop.startswith("# BD Pipeline Stall Radar — 1 warm stall, 1 aging, 2 never contacted"))
check("a never-contacted finding states the fact and carries no day count",
      "**A never** — FACT: Stage Prospect, never contacted." in prop and "Noned" not in prop)
check("the Task prose no longer claims active-stage scope",
      "active-stage" not in prop and "Stage-Prospect" in prop)
row = k.state_row(stalls, TODAY)
check("state row records never-contacted rows so the dedup window sees them",
      row["stalls"] == ["warm", "old", "A never", "B never"] and row["date"] == "2026-09-11")

print("--- dedup: repo-owned JSONL state, never ~/.hermes (T6.1) ---")


def with_state(rows, fn):
    home = tempfile.mkdtemp()
    state = pathlib.Path(home) / "var" / "bd-stall-radar" / "flagged.jsonl"
    if rows is not None:
        state.parent.mkdir(parents=True)
        state.write_text("".join(r + "\n" for r in rows), encoding="utf-8")
    old = {k_: os.environ.get(k_) for k_ in ("BD_STALL_RADAR_STATE", "HOME")}
    os.environ["BD_STALL_RADAR_STATE"] = str(state)
    os.environ["HOME"] = home
    try:
        return fn(state, pathlib.Path(home))
    finally:
        for k_, v in old.items():
            if v is None:
                os.environ.pop(k_, None)
            else:
                os.environ[k_] = v


def _row(date, stalls):
    return json.dumps({"date": date, "run": date + "T05:00:00+02:00", "stalls": stalls})


# (::radar-dedup-reads-state)
got = with_state([_row("2026-09-10", ["Acme", "Beta"])], lambda s, h: k.recently_flagged(TODAY))
check("a run recorded yesterday suppresses its names", got == {"Acme", "Beta"})

# (::radar-dedup-window)
got = with_state([_row("2026-09-08", ["Old"]), _row("2026-09-07", ["Older"]), "not json",
                  _row("2026-09-09", ["Recent"])],
                 lambda s, h: k.recently_flagged(TODAY))
check("3 days ago is inside the window, 4 is outside, a malformed row is skipped",
      got == {"Old", "Recent"})

# (::radar-dedup-absent-is-empty)
got = with_state(None, lambda s, h: (k.recently_flagged(TODAY), s.exists()))
check("an absent state file yields no dedup and creates nothing", got == (set(), False))


def _append_then_read(state, home):
    k.record_run(stalls, TODAY)
    lines = state.read_text(encoding="utf-8").splitlines()
    return lines, k.recently_flagged(TODAY), home


# (::radar-dedup-appends-one-line)
lines, seen, home = with_state(None, _append_then_read)
check("a run appends exactly one JSON line, creating the directory",
      len(lines) == 1 and json.loads(lines[0])["stalls"] == ["warm", "old", "A never", "B never"])
check("the line it wrote is what the next run reads back",
      seen == {"warm", "old", "A never", "B never"})
# (::radar-dedup-never-touches-hermes)
check("nothing under ~/.hermes is read or created", not (home / ".hermes").exists())
lines2, _, _ = with_state([_row("2026-09-10", ["X"])], _append_then_read)
check("an existing file gains one line, keeps the rest", len(lines2) == 2 and "X" in lines2[0])

print("--- run date: RUN_DATE, never the clock, when the runner exported one ---")
# (::kernel-date-matched-the-run) agent_propose.sh exports RUN_DATE once; the kernel used to
# take dt.date.today(), which crosses midnight ahead of it at a late slot.
check("RUN_DATE dates the run", k.run_date({"RUN_DATE": "2026-09-21"}) == dt.date(2026, 9, 21))
check("no RUN_DATE falls back to the clock", k.run_date({}) == dt.date.today())
check("a malformed RUN_DATE falls back to the clock rather than crashing the run",
      k.run_date({"RUN_DATE": "21-09-2026"}) == dt.date.today())

print("--- run summary: the kernel writes its own audit lines beside the state ---")
# (::radar-summary-is-kernel-written)
summary = k.summary_lines(list(range(88)), stalls + stalls, stalls, "some priorities", TODAY)
check("the summary line carries the counts the contract checks read",
      summary == ["bd-stall-radar (deterministic) 2026-09-11 — 88 deals, 8 Prospect&unworked, "
                  "4 flagged (1 warm, 1 aging, 2 never contacted)"])
check("empty priorities add the degraded warning, a second line",
      k.summary_lines([], [], [], "", TODAY)[1:] ==
      ["[warn] current_priorities.md empty via qmd — suppression degraded"])


def _write_summary(state, home):
    k.record_summary(summary)
    f = state.parent / "last-run.log"
    return f.exists(), f.read_text(encoding="utf-8") if f.exists() else ""


exists, text = with_state(None, _write_summary)
check("record_summary lands last-run.log beside flagged.jsonl, creating the directory",
      exists and text == summary[0] + "\n")

print()
if failures:
    print(f"FAIL: {len(failures)} check(s) failed")
    raise SystemExit(1)
print("all checks passed")
