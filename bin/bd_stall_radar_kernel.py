#!/usr/bin/env python3
"""BD Pipeline Stall Radar — deterministic kernel (NUC-24 / local tier).

Fully deterministic: NO model inference, NO API egress ($0). Replaces the
Hermes-wrapped claudius run for this standing job with exact rules over the
Notion Client Pipeline.

Why no model: the 2026-07-20 pilot ran the parked-vs-stalled judgment through
the on-box qwen3:8b and it was unreliable — it hallucinated "counterparty-owned"
parks for deals not in the priorities doc, and failed to suppress the hottest
active thread (right evidence, wrong boolean). The signals it was guessing at are
available structurally, so we take them deterministically instead.

Rules (all exact):
  candidate : Stage active AND last_contact != null AND days_silent > 7
  suppress  : company is named in current_priorities.md (Dave is actively
              managing it) OR Next action date is in the future (scheduled)
  aging tag : days_silent > 60 -> likely cold rather than a warm stall
  => proposal lists the remaining stalls; else a clean decline.

Deliberate parks / dead deals are already excluded upstream by the Stage guard
(On Hold / Closed are not active stages).

Contract (unchanged, matches agent_propose.sh): CWD is the inbox worktree;
writes ONE dated proposal to _inbox/agents/YYYY-MM-DD_bd-stall-radar.md or
nothing; prints a run summary to stdout (the Discord notification); appends one
episodic line to the claudius memory store for dedup. --dry-run touches no files.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request

DATA_SOURCE = "e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e"  # Notion Client Pipeline
NOTION_VERSION = "2025-09-03"
ACTIVE_STAGES = {"Prospect", "Qualified", "Proposal", "Active"}
STALL_DAYS = 7    # strictly greater-than
AGING_FLOOR = 60  # silent longer than this => likely cold, tagged (still flagged)
PRIORITIES_PATH = "04_operations/current_priorities.md"
MEM_FILE = os.path.expanduser("~/.hermes/profiles/claudius/memories/MEMORY.md")
DEDUP_WINDOW_DAYS = 3

# Tokens too generic to identify a company inside the priorities prose. A name is
# matched only on a distinctive token (>= 6 chars, word-boundary) not in this set,
# so a shared word like "logistics" or a bare first name never triggers suppression.
GENERIC_TOKENS = {
    "logistics", "logistiek", "netherlands", "nederland", "holding", "group",
    "coldstore", "global", "control", "transport", "international", "solutions",
    "warehousing", "terminals", "shipping", "consulting", "benelux", "europe",
}


# ── Notion ────────────────────────────────────────────────────────────────
def _plain(prop):
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in (v or []))
    if t in ("select", "status"):
        return (v or {}).get("name")
    if t == "date":
        return (v or {}).get("start")
    if t == "formula":
        f = v or {}
        return f.get(f.get("type"))
    return None


def fetch_deals(token):
    body = json.dumps({"page_size": 100}).encode()
    req = urllib.request.Request(
        f"https://api.notion.com/v1/data_sources/{DATA_SOURCE}/query",
        data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Notion-Version": NOTION_VERSION,
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("object") == "error":
        raise RuntimeError(f"notion error: {payload.get('code')} {payload.get('message')}")
    deals = []
    for row in payload.get("results", []):
        p = row["properties"]
        deals.append({
            "client": _plain(p.get("Client", {})) or "(unnamed)",
            "stage": _plain(p.get("Stage", {})),
            "last_contact": _plain(p.get("Last contact", {})),
            "days_formula": _plain(p.get("Days since last contact", {})),
            "next_action_date": _plain(p.get("Next action date", {})),
            "trigger": (_plain(p.get("Trigger event", {})) or "").strip(),
        })
    return deals


# ── qmd ───────────────────────────────────────────────────────────────────
def get_priorities():
    """current_priorities.md via qmd, stripped of the header + line-number gutter."""
    out = subprocess.run(["qmd", "get", PRIORITIES_PATH],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        return ""
    lines = [m.group(1) for m in
             (re.match(r"^\s*\d+:\s?(.*)$", ln) for ln in out.stdout.splitlines()) if m]
    return "\n".join(lines).strip()


# ── exact decision rules ──────────────────────────────────────────────────
def days_silent(deal, today):
    if isinstance(deal["days_formula"], (int, float)):
        return int(deal["days_formula"])
    lc = deal["last_contact"]
    if not lc:
        return None
    try:
        return (today - dt.date.fromisoformat(lc[:10])).days
    except ValueError:
        return None


def is_candidate(deal, today):
    """Active-stage deal with a REAL prior dialogue (non-null last contact) that has
    gone silent > 7 days. Never-contacted prospects (null last contact) are cold-list
    entries, not stalls, and are excluded."""
    if deal["stage"] not in ACTIVE_STAGES:
        return False, "non-active stage"
    if not deal["last_contact"]:
        return False, "never contacted"
    ds = days_silent(deal, today)
    if ds is None:
        return False, "unparseable last-contact date"
    if ds <= STALL_DAYS:
        return False, f"recent ({ds}d)"
    return True, f"silent {ds}d"


def named_in_priorities(client, priorities_lc):
    """True if a distinctive token of the company name appears in current_priorities.md
    -> Dave is actively managing/tracking it this week, so it is not a forgotten stall.
    Distinctive = >= 6 chars, word-boundary, not a generic industry word."""
    base = re.sub(r"\(.*?\)", " ", client).lower()
    for tok in re.split(r"[^a-z0-9]+", base):
        if len(tok) >= 6 and tok not in GENERIC_TOKENS \
                and re.search(r"\b" + re.escape(tok) + r"\b", priorities_lc):
            return tok
    return None


def next_action_future(deal, today):
    na = deal["next_action_date"]
    if not na:
        return False
    try:
        return dt.date.fromisoformat(na[:10]) > today
    except ValueError:
        return False


def suppression(deal, priorities_lc, today):
    """Reason to NOT flag this silent deal, or None if it is a genuine stall."""
    hit = named_in_priorities(deal["client"], priorities_lc)
    if hit:
        return f"actively managed (named in priorities: '{hit}')"
    if next_action_future(deal, today):
        return f"scheduled (next action {deal['next_action_date']})"
    return None


# ── memory dedup ──────────────────────────────────────────────────────────
def recently_flagged(today):
    if not os.path.exists(MEM_FILE):
        return set()
    flagged = set()
    with open(MEM_FILE, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for entry in text.split("\n§\n"):
        m = re.search(r"\[run:(\d{4}-\d{2}-\d{2})", entry)
        if not m or "bd-stall-radar" not in entry:
            continue
        try:
            when = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if (today - when).days > DEDUP_WINDOW_DAYS:
            continue
        sm = re.search(r"stalls_found=([^;]*)", entry)
        if sm:
            for tok in sm.group(1).split(","):
                name = tok.split(":")[0].strip()
                if name and name.lower() not in ("none", ""):
                    flagged.add(name)
    return flagged


def append_memory(line):
    try:
        import fcntl
        with open(MEM_FILE + ".lock", "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            existing = ""
            if os.path.exists(MEM_FILE) and os.path.getsize(MEM_FILE):
                with open(MEM_FILE, encoding="utf-8", errors="replace") as fh:
                    existing = fh.read()
            with open(MEM_FILE, "w", encoding="utf-8") as fh:
                fh.write(f"{existing}\n§\n{line}" if existing else line)
    except Exception as e:  # fail-soft: memory is best-effort, never blocks a run
        print(f"[warn] memory append failed: {e}", file=sys.stderr)


# ── proposal ──────────────────────────────────────────────────────────────
def build_proposal(stalls, today, n_deals):
    warm = [s for s in stalls if not s["aging"]]
    lines = [f"# BD Pipeline Stall Radar — {len(warm)} warm stall"
             f"{'s' if len(warm) != 1 else ''}"
             f"{f', {len(stalls) - len(warm)} aging' if len(stalls) - len(warm) else ''}"
             f" ({today}, claudius/deterministic)",
             "target: vault", "",
             "## Task",
             f"Standing BD stall radar (NUC-24) over {n_deals} Client Pipeline deals: "
             f"flag active-stage deals silent >{STALL_DAYS} days that Dave is not "
             "already managing. Deterministic run — no model inference, $0 API.",
             "", "## Key findings (fact vs inference labeled)"]
    for s in stalls:
        na = f" Next action {s['next_action_date']}." if s["next_action_date"] else ""
        trig = f" {s['trigger'][:160]}" if s["trigger"] else ""
        tag = (" **[aging — >60d silent, likely cold rather than a warm stall; "
               "consider Closed/On Hold]**" if s["aging"] else "")
        lines.append(
            f"- **{s['client']}** — FACT: Stage {s['stage']}, last contact "
            f"{s['last_contact']} ({s['days']}d silent).{na}{trig}{tag}")
    lines += ["", "## Implications for Vantage Point",
              "Warm stalls are engaged threads that have gone quiet past the threshold "
              "and are not in this week's focus — each is a candidate for one concrete "
              "re-engagement touch (Priority 1). Aging entries are single-touch prospects "
              "that never progressed; decide to work or retire them (Closed/On Hold).",
              "", "## Proposed vault change (target canonical file + exact content)",
              "None — flag only. Pipeline-state changes (Last contact / Stage / "
              "Blocked reason) are Dave's call from the Mac.",
              "", "## Confidence & gaps",
              "- Stage guard, non-null-contact guard, >7-day recency, and the 'named in "
              "current_priorities.md' suppression are all computed exactly — no model, "
              "no false positives from inference.",
              "- Suppression relies on the priorities doc naming actively-managed deals "
              "and on Notion field hygiene (e.g. a stale Last-contact date reads as more "
              "silent than reality). Verify borderline items.",
              "- Never-contacted cold-list prospects (null last contact) are excluded by "
              "design; this radar covers deals with a real prior dialogue only."]
    return "\n".join(lines) + "\n"


def memory_line(stalls, today, proposal_name):
    found = ",".join(f"{s['client']}:{s['days']}" for s in stalls) or "none"
    prop = proposal_name or "none: no genuine stalls"
    return (f"[run:{today.isoformat()}] task=bd-stall-radar; stalls_found={found}; "
            f"proposal={prop}; runtime=deterministic-kernel($0,no-LLM); "
            f"gaps=suppression-relies-on-priorities-naming+field-hygiene")


# ── orchestration ─────────────────────────────────────────────────────────
def classify(today):
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        raise RuntimeError("NOTION_API_TOKEN not in environment")
    deals = fetch_deals(token)
    priorities_lc = get_priorities().lower()
    already = recently_flagged(today)
    candidates = []
    for d in deals:
        if not is_candidate(d, today)[0]:
            continue
        d["days"] = days_silent(d, today)
        reason = suppression(d, priorities_lc, today)
        candidates.append({**d, "suppress": reason, "aging": d["days"] > AGING_FLOOR,
                           "dedup": d["client"] in already})
    stalls = [c for c in candidates if not c["suppress"] and not c["dedup"]]
    stalls.sort(key=lambda c: (c["aging"], -c["days"]))  # warm (actionable) first, then aging by age
    return deals, candidates, stalls, priorities_lc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="classify and print; write no files")
    args = ap.parse_args()
    today = dt.date.today()

    deals, candidates, stalls, priorities_lc = classify(today)
    warm = sum(1 for s in stalls if not s["aging"])

    print(f"bd-stall-radar (deterministic) {today} — {len(deals)} deals, "
          f"{len(candidates)} active&silent, {len(stalls)} flagged "
          f"({warm} warm, {len(stalls) - warm} aging)")
    if not priorities_lc:
        print("[warn] current_priorities.md empty via qmd — suppression degraded")
    for c in candidates:
        if c["suppress"]:
            tag = "SKIP"
        elif c["dedup"]:
            tag = "DEDUP"
        elif c["aging"]:
            tag = "AGING"
        else:
            tag = "STALL"
        note = c["suppress"] or ("already flagged <3d" if c["dedup"] else "")
        print(f"  [{tag:6}] {c['client'][:34]:34} {c['stage']:9} {c['days']:>4}d  {note[:52]}")

    if not stalls:
        print("=> clean decline: no genuine new stalls, no proposal written")
        if not args.dry_run:
            append_memory(memory_line([], today, None))
        return 0

    name = f"{today.isoformat()}_bd-stall-radar.md"
    proposal = build_proposal(stalls, today, len(deals))
    if args.dry_run:
        print(f"\n--- would write _inbox/agents/{name} ---\n\n{proposal}")
        return 0

    out_dir = os.path.join(os.getcwd(), "_inbox", "agents")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
        fh.write(proposal)
    append_memory(memory_line(stalls, today, name))
    print(f"=> wrote _inbox/agents/{name} ({len(stalls)} flagged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
