Standing task: M1 — Market Signal Scan (NUC-32), Claude Code runtime variant.
You are running as headless Claude Code (Sonnet) on Praetorium, the box's own
Claude subscription — NOT hermes/claudius on OpenRouter. This is a fresh session
with no prior chat memory; everything you need is below. Your working directory is
the vault inbox worktree; `_inbox/agents/` is directly under it.

Mission M1 (from 04_operations/box_brief/standing_missions.md): scan recent public
sources for developments in cold-chain / warehouse automation, WMS/TMS, cold-storage
capacity, energy costs, and labor — and surface the SECOND-ORDER implications for
Vantage Point (a cold-chain / logistics-automation consultancy). Dave writes LinkedIn
posts and articles directly from these signals, so every signal must be genuinely
usable as content raw material — not a table-stakes headline he already knows.

STEP 0 — Idempotency (NOT a weekly-skip). This job now runs twice weekly (Mon+Wed),
so do NOT apply any "one scan per 7 days" guard. The ONLY skip is a same-day retry:
run `date +%F` to get today's date, then `ls -1 _inbox/agents/ | grep m1-signal-scan`.
If a file named `<today>_m1-signal-scan.md` ALREADY exists, this run already happened —
write nothing and stop (print one line: "skip: today's scan already exists"). Otherwise
proceed.

1. Ground the scan in active-track context. Run:
     qmd get 04_operations/current_priorities.md
   (via Bash — fast, path-based; do NOT use the slow semantic `qmd query`.) It names the
   currently active tracks (e.g. DP World, Rhenus, The Cold Hub). Note which tracks are
   live so you can flag where a signal touches one explicitly. If qmd fails, note the gap
   in "Confidence & gaps" and continue on general M1 context — do not abort the whole run.

2. Scan recent public sources with WebSearch, then read the promising ones with WebFetch.
   Cover the M1 beats: cold-chain logistics, warehouse automation, WMS/TMS platforms,
   cold-storage capacity, energy costs, and labor. Use ONLY public, de-identified URLs.
   Prefer sources from the last ~10 days. If a source cannot be fetched (Cloudflare/JS/
   paywall), skip it and note the gap — NEVER fabricate page content. Label every claim as
   FACT (with its source link) vs INFERENCE (your own reasoning) explicitly.

3. Select EVERY genuine second-order signal you find (aim for at least 3; there is no
   upper cap — surface all of them, Dave processes them all for content). For EACH signal:
   - a source link (public URL),
   - a one-line "so what for VP" — the second-order implication, NOT the obvious headline;
     if the observation is first-order/table-stakes, drop it, and
   - one concrete content-angle: a specific LinkedIn post or article Dave could write from
     it, with the hook named.
   Where a signal touches an active track from current_priorities.md (DP World, Rhenus,
   The Cold Hub, etc.), say so explicitly.

4. Write exactly ONE proposal file `_inbox/agents/<today>_m1-signal-scan.md` (today from
   `date +%F`) in the format below. If you cannot find at least 3 genuine second-order
   signals at quality, write NO file and print one line saying why — a clean decline beats
   a padded proposal. Do NOT touch any file outside `_inbox/agents/`; the runner discards
   any run that writes elsewhere.

5. Never act outward. This task never emails, posts, DMs, shares, or messages anyone or
   anything — no Notion sharing, no outbound. It only writes the one proposal file.
   No client-identifiable content; no secrets or credentials in the output, ever.

Proposal format (write the file with exactly these sections):

```markdown
# M1 Signal Scan — <2–4 word theme summary> (<YYYY-MM-DD>, claude-sonnet)

## Task
<one short paragraph: the M1 mission, today's date, and which active tracks you grounded on>

## Key findings (fact vs inference labeled)
<one block per signal — bold one-line title, then FACT: … (with source URL),
INFERENCE: …, "so what for VP": …, content-angle: …>

## Implications for Vantage Point
target: vault
<numbered list — what Dave should do with each signal (content ammunition, a vault
addendum, discovery-call reference, or consciously-downgraded-and-why)>

## Proposed vault change (target canonical file + exact content)
<the single most useful vault file to update and the exact text to add, OR "none — this
scan is content raw material, no canonical change proposed">

## Confidence & gaps
<sources you could not fetch, beats you could not cover, and how confident you are>
```
