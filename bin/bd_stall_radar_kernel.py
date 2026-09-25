#!/usr/bin/env python3
"""BD Pipeline Stall Radar — deterministic kernel (NUC-24 / local tier).

Fully deterministic: NO model inference, NO API egress ($0). Replaced the
model-driven claudius run for this standing job (2026-07-20) with exact rules
over the Notion Client Pipeline.

Why no model: the 2026-07-20 pilot ran the parked-vs-stalled judgment through
the on-box qwen3:8b and it was unreliable — it hallucinated "counterparty-owned"
parks for deals not in the priorities doc, and failed to suppress the hottest
active thread (right evidence, wrong boolean). The signals it was guessing at are
available structurally, so we take them deterministically instead.

Rules (all exact):
  candidate : Stage == Prospect AND (never contacted OR days_silent > 7)
  suppress  : company is named in current_priorities.md, matched on its full
              normalised name (Dave is actively managing it) OR Next action
              date is in the future (scheduled)
  aging tag : days_silent > 60 -> likely cold rather than a warm stall
  never tag : no Last contact at all -> a lead nobody has opened yet
  => proposal lists what survives; else a clean decline.

Scope (Dave, 2026-09-11): this radar surfaces the BD work Dave is NOT doing.
Qualified / Proposal / Active rows are the accounts he is working, and listing
them is what made the report unread, so they are out of scope by design; On
Hold / Closed never were in scope. Never-contacted Prospect rows are included
on the same reasoning: unopened is the most unworked a lead can be.

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
IN_SCOPE_STAGES = {"Prospect"}  # the rest are being worked; see module docstring
STALL_DAYS = 7    # strictly greater-than
AGING_FLOOR = 60  # silent longer than this => likely cold, tagged (still flagged)
PRIORITIES_PATH = "04_operations/current_priorities.md"
DEFAULT_STATE_FILE = "~/agent-workforce/var/bd-stall-radar/flagged.jsonl"
DEDUP_WINDOW_DAYS = 3

# Tokens that never identify a company on their own. A name is matched on its
# full normalised form first; the short form drops these tokens so that
# "Rhenus Logistics" still finds "Rhenus", while "Embassy Freight Rotterdam" can
# never match the city alone (measured 2026-09-11: suppressed on 'rotterdam'
# against unrelated prose). City names are a floor here, not the fix.
GENERIC_TOKENS = {
    "the", "logistics", "logistiek", "netherlands", "nederland", "holding", "group",
    "coldstore", "global", "control", "transport", "international", "solutions",
    "warehousing", "terminals", "shipping", "consulting", "benelux", "europe",
    "contract", "freight", "cargo", "food", "cold", "chain", "services",
    "rotterdam", "amsterdam", "antwerpen", "antwerp", "tilburg", "venlo",
    "eindhoven", "utrecht", "breda", "schiphol", "moerdijk", "waalwijk",
    "nijmegen", "zwolle", "arnhem", "groningen", "duisburg", "hamburg",
}
LEGAL_SUFFIXES = {"bv", "nv", "cv", "vof", "bvba", "gmbh", "ag", "ltd", "plc",
                  "inc", "llc", "sa", "srl", "sarl", "ab", "oy", "aps"}
MIN_SHORT_FORM = 6   # chars; the old single-token floor, kept for the short form
PHRASE_WINDOW = 6    # max words a folded company name may span in the prose
# Lowercase words allowed inside a capitalised name phrase ("Jan de Rijk").
NAME_PARTICLES = {"de", "den", "der", "van", "von", "du", "le", "la", "en", "of", "and", "the"}


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
    """In-scope (Prospect) deal that is not being worked: either never contacted at
    all, or with a real prior dialogue that has gone silent > 7 days."""
    if deal["stage"] not in IN_SCOPE_STAGES:
        return False, "out-of-scope stage"
    if not deal["last_contact"]:
        return True, "never contacted"
    ds = days_silent(deal, today)
    if ds is None:
        return False, "unparseable last-contact date"
    if ds <= STALL_DAYS:
        return False, f"recent ({ds}d)"
    return True, f"silent {ds}d"


def _name_tokens(client):
    base = re.sub(r"\(.*?\)", " ", client).lower().replace(".", "")
    tokens = [t for t in re.split(r"[^a-z0-9]+", base) if t]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return tokens


def name_forms(client):
    """Folded forms of a company name, most specific first: the full name with
    parentheticals and legal suffixes dropped, then (if distinct and long enough)
    the name with generic tokens dropped too. Whitespace is folded away so Notion's
    "The ColdHub" and the vault's "The Cold Hub" are the same string."""
    tokens = _name_tokens(client)
    forms = []
    if tokens:
        forms.append(("".join(tokens), " ".join(tokens)))
    core = [t for t in tokens if t not in GENERIC_TOKENS]
    if core and core != tokens and len("".join(core)) >= MIN_SHORT_FORM:
        forms.append(("".join(core), " ".join(core)))
    return forms


def _is_name_word(word):
    return word[0].isupper() or word[0].isdigit()


def _is_name_phrase(words):
    """A company mention is capitalised; prose is not. Folding whitespace away made
    "RealCold" equal "the real cold-storage risk" (measured 2026-09-11), so a window
    only counts when every word is capitalised, a digit, or a name particle."""
    return any(_is_name_word(w) for w in words) and \
        all(_is_name_word(w) or w in NAME_PARTICLES for w in words)


def priority_phrases(priorities):
    """Every capitalised run of 1..PHRASE_WINDOW consecutive words in the prose,
    folded the same way as name_forms, so a match is always on whole words."""
    words = re.findall(r"[A-Za-z0-9]+", priorities)
    phrases = set()
    for i in range(len(words)):
        for k in range(1, PHRASE_WINDOW + 1):
            window = words[i:i + k]
            if _is_name_phrase(window):
                phrases.add("".join(window).lower())
    return phrases


def named_in_priorities(client, phrases):
    """The readable form of the company name that appears in current_priorities.md
    -> Dave is actively managing/tracking it this week, so it is not a forgotten
    stall. None when no form matches. A Notion title that carries a descriptor after
    the company name will not match its priorities heading; that fails towards
    surfacing the row, which is the cheap direction."""
    for folded, readable in name_forms(client):
        if folded in phrases:
            return readable
    return None


def next_action_future(deal, today):
    na = deal["next_action_date"]
    if not na:
        return False
    try:
        return dt.date.fromisoformat(na[:10]) > today
    except ValueError:
        return False


def suppression(deal, phrases, today):
    """Reason to NOT flag this unworked deal, or None if it is a genuine stall."""
    hit = named_in_priorities(deal["client"], phrases)
    if hit:
        return f"actively managed (named in priorities: '{hit}')"
    if next_action_future(deal, today):
        return f"scheduled (next action {deal['next_action_date']})"
    return None


# ── run-state dedup ───────────────────────────────────────────────────────
# One JSON line per run: {"date": "YYYY-MM-DD", "run": "<iso ts>", "stalls": [names]}.
def state_path():
    return os.path.expanduser(os.environ.get("BD_STALL_RADAR_STATE") or DEFAULT_STATE_FILE)


def _state_rows(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                yield dt.date.fromisoformat(row["date"]), list(row["stalls"])
            except (ValueError, KeyError, TypeError) as e:
                print(f"[warn] skipping malformed state row: {e}", file=sys.stderr)


def recently_flagged(today):
    path = state_path()
    if not os.path.exists(path):
        return set()
    flagged = set()
    for when, stalls in _state_rows(path):
        if (today - when).days <= DEDUP_WINDOW_DAYS:
            flagged.update(n for n in stalls if n)
    return flagged


def state_row(stalls, today):
    return {"date": today.isoformat(), "run": dt.datetime.now().astimezone().isoformat(),
            "stalls": [s["client"] for s in stalls]}


def record_run(stalls, today):
    path = state_path()
    try:
        import fcntl
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".lock", "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(state_row(stalls, today)) + "\n")
    except Exception as e:  # fail-soft: state is best-effort, never blocks a run
        print(f"[warn] state append failed: {e}", file=sys.stderr)


# ── run summary ───────────────────────────────────────────────────────────
# The audit lines the contract checks read (kernel-actually-ran, deal-count-was-not-zero,
# priorities-suppression-was-live). Written by the kernel itself, beside the dedup state,
# because the agent's final reply is the only other place they could appear and the agent
# is free to paraphrase it.
def summary_path():
    return os.path.join(os.path.dirname(state_path()), "last-run.log")


def summary_lines(deals, candidates, stalls, priorities, today):
    warm, aging, never = _counts(stalls)
    lines = [f"bd-stall-radar (deterministic) {today} — {len(deals)} deals, "
             f"{len(candidates)} Prospect&unworked, {len(stalls)} flagged "
             f"({warm} warm, {aging} aging, {never} never contacted)"]
    if not priorities:
        lines.append("[warn] current_priorities.md empty via qmd — suppression degraded")
    return lines


def record_summary(lines):
    path = summary_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("".join(line + "\n" for line in lines))
        os.replace(tmp, path)
    except Exception as e:  # fail-soft, like the state append
        print(f"[warn] summary write failed: {e}", file=sys.stderr)


# ── proposal ──────────────────────────────────────────────────────────────
def _counts(stalls):
    never = sum(1 for s in stalls if s["never"])
    aging = sum(1 for s in stalls if s["aging"])
    return len(stalls) - never - aging, aging, never


def _headline(stalls):
    warm, aging, never = _counts(stalls)
    parts = [f"{warm} warm stall{'s' if warm != 1 else ''}"]
    if aging:
        parts.append(f"{aging} aging")
    if never:
        parts.append(f"{never} never contacted")
    return ", ".join(parts)


def _finding(s):
    na = f" Next action {s['next_action_date']}." if s["next_action_date"] else ""
    trig = f" {s['trigger'][:160]}" if s["trigger"] else ""
    if s["never"]:
        return (f"- **{s['client']}** — FACT: Stage {s['stage']}, never contacted."
                f"{na}{trig} **[never contacted — no dialogue yet; open it or retire it]**")
    tag = (" **[aging — >60d silent, likely cold rather than a warm stall; "
           "consider Closed/On Hold]**" if s["aging"] else "")
    return (f"- **{s['client']}** — FACT: Stage {s['stage']}, last contact "
            f"{s['last_contact']} ({s['days']}d silent).{na}{trig}{tag}")


def build_proposal(stalls, today, n_deals):
    lines = [f"# BD Pipeline Stall Radar — {_headline(stalls)}"
             f" ({today}, claudius/deterministic)",
             "target: vault", "",
             "## Task",
             f"Standing BD stall radar (NUC-24) over {n_deals} Client Pipeline deals: "
             f"flag Stage-Prospect deals that are not being worked — silent >{STALL_DAYS} "
             "days, or never contacted — and that Dave is not already managing. "
             "Qualified / Proposal / Active are out of scope by design: those are the "
             "accounts being worked. Deterministic run — no model inference, $0 API.",
             "", "## Key findings (fact vs inference labeled)"]
    lines += [_finding(s) for s in stalls]
    lines += ["", "## Implications for Vantage Point",
              "Warm stalls are engaged threads that have gone quiet past the threshold "
              "and are not in this week's focus — each is a candidate for one concrete "
              "re-engagement touch (Priority 1). Aging entries are single-touch prospects "
              "that never progressed; decide to work or retire them (Closed/On Hold). "
              "Never-contacted rows are leads nobody has opened: each is a cold first "
              "touch to write, or a row to retire.",
              "", "## Proposed vault change (target canonical file + exact content)",
              "None — flag only. Pipeline-state changes (Last contact / Stage / "
              "Blocked reason) are Dave's call from the Mac.",
              "", "## Confidence & gaps",
              "- Stage scope, >7-day recency, the never-contacted rule and the 'named in "
              "current_priorities.md' suppression are all computed exactly — no model, "
              "no false positives from inference.",
              "- Suppression matches the full normalised company name against the "
              "priorities doc (whitespace and legal suffixes folded), so a Notion title "
              "that carries a descriptor after the company name will not match its "
              "heading and surfaces here instead. It also relies on Notion field hygiene "
              "(a stale Last-contact date reads as more silent than reality). Verify "
              "borderline items.",
              "- Never-contacted Prospect rows are included (Dave, 2026-09-11). Qualified "
              "/ Proposal / Active rows are excluded by design — this radar covers the "
              "work not being done, not the accounts being worked."]
    return "\n".join(lines) + "\n"


# ── orchestration ─────────────────────────────────────────────────────────
def classify(today):
    token = os.environ.get("NOTION_API_TOKEN")
    if not token:
        raise RuntimeError("NOTION_API_TOKEN not in environment")
    deals = fetch_deals(token)
    priorities = get_priorities()
    phrases = priority_phrases(priorities)
    already = recently_flagged(today)
    candidates = []
    for d in deals:
        if not is_candidate(d, today)[0]:
            continue
        d["days"] = days_silent(d, today)
        never = not d["last_contact"]
        candidates.append({**d, "suppress": suppression(d, phrases, today),
                           "never": never,
                           "aging": not never and d["days"] > AGING_FLOOR,
                           "dedup": d["client"] in already})
    stalls = [c for c in candidates if not c["suppress"] and not c["dedup"]]
    # warm (actionable) first, then aging by age, then never-contacted by name
    stalls.sort(key=lambda c: (c["never"], c["aging"], -(c["days"] or 0), c["client"].lower()))
    return deals, candidates, stalls, priorities


def run_date(env=None):
    """The date of this run: RUN_DATE, exported once by agent_propose.sh for every step, so the
    proposal's filename and the checks keyed on it cannot straddle midnight. dt.date.today()
    only when the kernel runs by hand."""
    raw = (os.environ if env is None else env).get("RUN_DATE", "").strip()
    if not raw:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        print(f"[warn] RUN_DATE={raw!r} is not YYYY-MM-DD — dating this run by the clock instead",
              file=sys.stderr)
        return dt.date.today()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="classify and print; write no files")
    args = ap.parse_args()
    today = run_date()

    deals, candidates, stalls, priorities = classify(today)

    summary = summary_lines(deals, candidates, stalls, priorities, today)
    print("\n".join(summary))
    if not args.dry_run:
        record_summary(summary)
    for c in candidates:
        if c["suppress"]:
            tag = "SKIP"
        elif c["dedup"]:
            tag = "DEDUP"
        elif c["never"]:
            tag = "NEVER"
        elif c["aging"]:
            tag = "AGING"
        else:
            tag = "STALL"
        note = c["suppress"] or ("already flagged <3d" if c["dedup"] else "")
        age = "never" if c["never"] else f"{c['days']}d"
        print(f"  [{tag:6}] {c['client'][:34]:34} {c['stage']:9} {age:>5}  {note[:52]}")

    if not stalls:
        print("DECLINE: no genuine new stalls, no proposal written")
        if not args.dry_run:
            record_run([], today)
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
    record_run(stalls, today)
    print(f"=> wrote _inbox/agents/{name} ({len(stalls)} flagged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
