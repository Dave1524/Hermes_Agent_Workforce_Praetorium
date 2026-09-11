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
import pathlib

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
mem = k.memory_line(stalls, TODAY, "x.md")
check("memory line records never-contacted rows so the dedup window sees them",
      "A never:never" in mem and "warm:22" in mem)

print()
if failures:
    print(f"FAIL: {len(failures)} check(s) failed")
    raise SystemExit(1)
print("all checks passed")
