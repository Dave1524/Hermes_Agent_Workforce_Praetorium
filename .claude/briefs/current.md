# Brief: Close the four carried work items, then retire the two content-research campaigns
**Date:** 2026-09-02   **Verify:** `bash bin/verify.sh` from the repo root (syntax + shellcheck -S error over `bin/`, then every `tests/*.sh`)

This is Phase-B brief 6, the last entry in `design/phaseb-brief-queue.toml`. It is two halves
with a hard gate between them:

- **W1–W4** — `design/open-decisions.md:867-870`. Executable now.
- **D5's campaign cleanup** — `design/open-decisions.md:449-464`. **Cannot execute before
  2026-09-04 01:30.** Both units are still firing.

**Four items, not five.** The Carried-work table lists W1–W5, but **W5 is done** — all 26
`[[workflows]]` entries already carry an explicit `status`, recorded at
`design/open-decisions.md:571` (`W5 (done, 3a52d42)`) and `design/eval-spec.md:165`. The stale
row at `design/open-decisions.md:871` is **brief 3's** edit
(`.claude/briefs/workflow-coverage-checker.md:93-96`); do not race it from here.

The queue declares this brief `ships = "green"`. That is a liability, not a comfort: **every
assertion added here passes the moment it lands, so none of it has been shown to detect
anything.** Criterion 14 is how that debt gets paid.

Read `design/open-decisions.md` § Carried work (line 861) and D5 (line 381), plus
`design/workflow-registry.md` §6.2-§6.6 (line 148), before starting.

## Acceptance criteria

1. **Episodic memory keys on the owner persona, and the six affected jobs stop logging
   `memory=no-store`.** `bin/agent_propose.sh:237` builds the store path from the *runtime
   profile* — `MEM_DIR="${RA_MEMORY_DIR:-$HOME/.hermes/profiles/$run_profile/memories}"` —
   and `$run_profile` is the model-named `AGENT_PROFILE` (`claude-opus` / `claude-sonnet`,
   resolved at `:178-183`). No such directory exists, so `:393-395` takes the `no-store` branch
   and the run's episodic record is dropped. Measured from `~/agent-workforce/logs/cost.log`
   on 2026-09-02, the six jobs are: `standing-research` (22 runs), `raw-ingest` (22),
   `m1-signal-scan` (12), `bd-followup-drafts` (11), `weekly-pre-assembly` (5),
   `knowledge-digest` (4). Owner comes from the manifest — the persona whose
   `design/agents/<name>.toml` declares that `[[workflows]]` entry.

2. **`~/.hermes/profiles/<persona>/memories` is the store, and nothing new has to be built to
   prune it.** `bin/consolidate_memory.sh:149` discovers `*/memories` under `PROFILES_ROOT`
   dynamically, and `marcus`, `claudius`, `augustus` and `trajan` all already have one. A fix
   that invents a new store location outside that glob silently opts out of nightly
   consolidation.

3. **The four ops-mode jobs still log `memory=na` after the change, and that is recorded, not
   left to be rediscovered.** `bin/agent_propose.sh:236` and `:368-372` make ops mode skip
   memory entirely by design (NUC-36) — `praetorium-daily-plan`, `praetorium-eod-summary`,
   `overnight-morning-report` and both campaigns log `na`, not `no-store`. So W1's note *"no
   scheduled persona workflow accumulates episodic memory today"*
   (`design/open-decisions.md:867`) is **still half-true after this brief**, for a different and
   deliberate reason. Correct that row to say which jobs the fix reaches and which are `na` by
   design. Do **not** make ops mode record memory to close the gap — that is a separate decision
   with its own evidence.

4. **The runner's fallback memory entry no longer hardcodes one persona.**
   `bin/agent_propose.sh:400` writes `task=standing claudius scheduled run` into *every* job's
   fallback record regardless of owner. After the fix it names the owning persona and the real
   task slug. This is the same defect as criterion 1 in a second place; fix both or the store
   is right and its contents are wrong.

5. **`AGENT_PROFILE`'s two consumers are separated, and the split is explicit.** The same
   variable feeds the memory path *and* the `profile=` column of the `schema=3` cost.log record
   (`bin/agent_propose.sh:98`), which `bin/run_record.sh:37` reads back and
   `tests/test_scorecard.sh:36-40` fixtures. Whatever shape the fix takes, the cost record must
   still say which *runtime* ran (that is what makes a model regression visible) **and** the
   memory must key on the *owner*. Silently repurposing `profile=` to mean owner loses the
   runtime and breaks the reader at `run_record.sh:37`.

6. **Every persona-workflow profile states its owner in one standard header line.** Twelve
   `[[workflows]]` entries carry a `profile` field (marcus 4, claudius 6, augustus 2 —
   the augustus pair disappears in the second half of this brief). Measured 2026-09-02, only
   **two** state an owner: `profiles/daily_plan_task.md:3` and `profiles/eod_summary_task.md:3`
   ("You are Marcus"). `profiles/bd_stall_radar_task.md:2` uses a third form ("You are the
   claudius box profile"), and the remaining nine state no owner at all — they state the
   *runtime* ("You are running as headless Claude Code (Opus 5)"). One form, on every one.

7. **A test asserts the header owner against the manifest that declares the workflow, in that
   direction.** For every `[[workflows]]` entry carrying `profile`, the named file exists and
   its header line names the `name` of the manifest it is declared in. **The trap this catches
   is live today:** `profiles/weekly_pre_assembly_cc_task.md:3` reads *"NOT hermes/claudius on
   OpenRouter"*, but `weekly-pre-assembly` is owned by **marcus**
   (`design/agents/marcus.toml`, decided `design/workflow-registry.md:58-60` §7.2). A header
   derived from prompt text rather than from the manifest gets this one wrong.

8. **The reporting jobs' unit lists have one owner, and the eight invisible units become
   visible.** Measured 2026-09-02, the `praetorium-*`-glob defect is in six files:
   `profiles/daily_plan_task.md:61`, `profiles/eod_summary_task.md:59`,
   `profiles/overnight_morning_report_cc_task.md:28`, `bin/overnight_pre_snapshot.sh:81-83`,
   `bin/praetorium-status.sh:7-11` and `:17-21`, and `bin/local_tier_eval.sh:51-52`. The best
   coverage of the six is the daily-plan glob at **9** standing units. Eight units appear in
   **none** of the six: `raw-ingest`, `knowledge-digest`, `m1-signal-scan`,
   `content-change-dispatch`, `fleet-eval`, `fleet-turn-check`, `inbox-backlog-alert`, and
   user-scope `buzz-pr-watch`. (`local-tier-eval` and `ttm-pool-drain` appear only inside
   `bin/local_tier_eval.sh`'s own service list — self-coverage, which is not coverage.)

9. **The denominator is defined in the check, not assumed.** The queue records the defect as
   *9 of 19* as measured on 2026-09-01. The numerator reproduces exactly; the denominator does
   not, because "19" never named its set — the manifests hold 26 `[[workflows]]` entries, 22
   `standing`, 21 of those system-scope (`buzz-pr-watch` is user scope,
   `design/agents/trajan.toml`). Pick the set, state it in the check, and let the number follow
   from it. A coverage ratio whose denominator is a remembered integer is the readiness-report
   class again.

10. **The generated list is a committed artifact in a deployed tree, never a runtime read of
    `design/`.** `bin/deploy:20` deploys exactly `bin profiles docs CLAUDE.md AGENTS.md
    README.md config systemd` — **`design/` is not among them and does not exist in
    `~/agent-workforce/`** (verified 2026-09-02). Anything that reads `design/agents/*.toml` at
    run time works from the repo and fails or silently empties in the tree systemd actually
    execs. This also keeps D4's posture: D4 chose (b) — literals kept, asserted against the
    manifest by a test — and rejected codegen precisely because *"generation would have to emit
    into both trees or it adds a third copy of the truth"* (`design/open-decisions.md:347-352`).
    One literal with one owner, checked; not six literals, and not a runtime lookup.

11. **The job-override examples have exactly one home, and every pointer at them agrees.**
    `config/job-overrides/` holds a `README.md` and an `archive/` of four stale examples that
    invoke retired runtimes; the live examples are the nine `profiles/*.env.example`.
    `docs/runbook.md` still points installers at the archived home in six places — `:10`, `:80`,
    `:109`, `:112`, `:226`, `:255` — and `:112` names
    `config/job-overrides/augustus-content.env.example`, which exists only under `archive/`.
    Following the runbook today provisions a runtime that no longer exists. After the change
    there is one home, one README, and no reference to the other.

12. **Both campaign units are gone from every tree that holds them, after their last firing,
    and the deletion is symmetric.** `praetorium-content-strategy-research.{service,timer}` and
    `praetorium-faceless-content-research.{service,timer}` exist **only** in
    `/etc/systemd/system/` — there is no source copy in `systemd/` (verified 2026-09-02;
    `design/agents/augustus.toml:104` and `:118` record the same as `§6.7`). So the deletion is
    four files in `/etc` plus the dated exclusion that brief 2 gave them, and nothing in
    `systemd/`. Brief 2 handed this here explicitly
    (`.claude/briefs/deploy-drift-check.md:254-257`).

13. **The campaigns' surviving record has a declared home, so a later cleanup cannot read it as
    an orphan.** When the units go, the only artifacts left are the two Notion pages and the
    counter at `~/agent-workforce/var/notion_research_pages.json`, maintained by
    `bin/notion_research_page.py:35,88-96`. Neither campaign ever produced a proposal
    (`proposal=none` on all rows, `AGENT_RUN_MODE=ops`). D5 item 3
    (`design/open-decisions.md:462-464`) requires this be noted in the registry. The two
    `[[workflows]]` entries must also be resolved rather than abandoned: `status = "campaign"`
    becomes `"spent"` when the last date fires (`design/agent-model.md:184` — *"every date has
    fired; no next elapse … flag for removal"*), and an entry left declaring a unit that exists
    in neither tree is a new red for brief 2's drift check.

14. **Every assertion added by this brief is demonstrated failing on a deliberately broken
    input before it is trusted.** Nothing here ships red, so nothing here has been shown to
    detect anything. For each new check: break the input in a scratch copy, watch it fail,
    restore. Named minimum — remove the owner header line from one profile (criterion 7 must
    fail); add a unit to the manifests and not to the generated list (criterion 8 must fail);
    point one runbook line back at the archived home (criterion 11 must fail). **Break the
    input, never the assertion.** Record what was broken and what failed.

15. **The W3 verification is scheduled for a day its failing case can occur.** The defect is
    correct by coincidence 5 days in 7: `m1-signal-scan` is the invisible unit with the
    narrowest schedule — `Mon,Wed 05:30` (`design/agents/claudius.toml`) — so on the other five
    days a report that omits it is indistinguishable from a correct one. Verify on a Monday or
    a Wednesday, or verify against a fixture that names the day. Do not read the schedule from
    `list-timers`; read the declared value from the manifest or `systemctl cat`
    (`design/agent-model.md:120`, `design/workflow-registry.md:69-74`).

16. `bash bin/verify.sh` exits 0.

## Files to create

- **One owner for the fleet unit list** — a single committed artifact under a tree
  `bin/deploy:20` actually deploys (`bin/`, `config/` or `profiles/`), listing the units the
  reporting jobs report on. It replaces six hand-maintained lists; it does not become a seventh.
  It must be derivable from `design/agents/*.toml` by a checker running in the repo, and
  readable without `design/` by anything running in `~/agent-workforce/`.

- **One test for W2 + W3** — `tests/<name>.sh`, asserting: every `[[workflows]]` entry with a
  `profile` names a file that exists and whose header line names the owning manifest
  (criterion 7); and the committed unit list equals the manifest-derived set for the stated
  status filter (criteria 8-10). Follow `tests/test_buzz_unit_wiring.sh` verbatim on structure —
  `set -uo pipefail`, the `assert()` helper that scopes `pipefail` **off** inside the condition,
  and the `yes | grep -q y` canary as the first assertion. That canary is load-bearing: under
  `pipefail` a condition ending in an early-exiting reader fails a true assertion and silently
  passes a negated one, which disabled a swathe of this gate until 2026-08-09 (`CLAUDE.md` §
  Verification).

- **Nothing else.** W1 and W4 are edits to files that exist; D5's half only deletes.

## Files to modify

**W1 — memory keying**
- `bin/agent_propose.sh:237` (`MEM_DIR`), `:178-183` (profile resolution), `:400` (the
  hardcoded `claudius` fallback entry). Keep `:98`'s `profile=` meaning the runtime
  (criterion 5).
- The nine `profiles/*.env.example` files that set `AGENT_PROFILE` — `daily_plan:11`,
  `eod_summary:7`, `knowledge_digest:16`, `m1_signal_scan:15`,
  `overnight_morning_report:12`, `raw_ingest:16`, `standing_research:21`,
  `weekly_pre_assembly:19`, `bd_followup_drafts:17` — plus the commented-out persona forms at
  `m1_signal_scan.env.example:23` and `standing_research.env.example:32`, which are the *old*
  scheme and will read as the fix if left in place.
- `~/.config/agent-workforce/*.env` is where these land at runtime. **It is deny-listed and
  outside this repo — you cannot read it and must not try.** State the required edit as a
  handoff step with the exact key and value per job, the way `docs/runbook.md` § Job wiring
  already does. Until Dave applies it, the live jobs keep the old keying: say so, do not
  assume it.
- `design/open-decisions.md:867` (the W1 row) — criterion 3.

**W2 — owner header**
- The ten persona profiles that lack a standard owner line: `standing_research_cc_task.md`,
  `raw_ingest_cc_task.md`, `m1_signal_scan_cc_task.md`, `knowledge_digest_cc_task.md`,
  `bd_followup_drafts_cc_task.md`, `bd_stall_radar_task.md`,
  `overnight_morning_report_cc_task.md`, `weekly_pre_assembly_cc_task.md`, and the two campaign
  profiles (`standing_research_content_strategy_task.md`,
  `standing_research_faceless_content_task.md`) **only if W2 lands before the D5 half deletes
  them** — if the gate has passed, skip them rather than editing a file about to go.
- `profiles/daily_plan_task.md:3` and `profiles/eod_summary_task.md:3` — already state an
  owner, in prose. Normalise to the one form; do not leave two.
- `design/agent-model.md` — the `[[workflows]]` schema block (line 117-132) gains the field or
  convention that makes the header assertable, if the chosen shape needs one.

**W3 — unit lists**
- The six files at the lines in criterion 8. Each stops carrying its own list.
- `design/open-decisions.md:869` (the W3 row).

**W4 — one example home**
- `config/job-overrides/README.md` — currently documents the mechanism correctly and then
  points at `profiles/` as a temporary measure.
- `docs/runbook.md:10, 80, 109, 112, 226, 255`.
- The nine `profiles/*.env.example` and the four `config/job-overrides/archive/*.env.example`,
  depending on which home wins. **Archive is history — a retired mention in an archived file is
  a correct record, not drift.** Do not "fix" the archived examples to name live runtimes.
- `design/open-decisions.md:870` (the W4 row), `design/workflow-registry.md:165-176` (§6.5).

**D5 — after the gate**
- `/etc/systemd/system/praetorium-content-strategy-research.{service,timer}` and
  `praetorium-faceless-content-research.{service,timer}` — deleted. **`/etc/systemd/system` is
  root-owned; this is Dave's action.** State it as a handoff with the exact commands
  (`systemctl disable --now`, `rm`, `daemon-reload`); do not attempt it and do not add `sudo`
  to any script in this repo.
- `design/agents/augustus.toml:92-118` — the two `[[workflows]]` entries (criterion 13).
- `design/workflow-registry.md` §4 or §5 — the campaigns' closing record: final `run_count`,
  the two Notion page ids, and the counter file's path.
- `design/open-decisions.md:449-464` — mark D5's three follow-ups discharged.

## Test plan

**What is red before the change, and how you see it**

1. **W1.** `grep -c 'memory=no-store' ~/agent-workforce/logs/cost.log` is non-zero today, and
   the six task slugs in criterion 1 account for all of it. The runner logs the reason verbatim
   at `bin/agent_propose.sh:395` — `MEMORY: no per-profile store at <path>`. After the fix, a
   run of any of the six logs `recorded` or `fallback`, and the store it names exists under
   `~/.hermes/profiles/<owner>/memories`. **`bd-followup-drafts` and `bd-stall-radar` are
   `dormant` — their timers are disabled** (`design/agents/claudius.toml`), so they produce no
   firing to observe; assert those two structurally from the env example and the manifest, and
   do not enable a timer to create evidence.

2. **W2.** The new assertion fails on `weekly_pre_assembly_cc_task.md` before the edit: the
   file names claudius and the manifest says marcus. That is a genuine pre-existing red, and it
   is the one case worth watching fail first.

3. **W3.** Before the change, the manifest-derived set minus the six files' union is the eight
   units in criterion 8. Assert that difference is exactly those eight *before* fixing, so the
   fix is measured against a recorded baseline rather than against itself. After the change the
   difference is empty for the declared status filter.

4. **W4.** `ls config/job-overrides/*.env.example` matches nothing today while
   `docs/runbook.md:112` names one of those paths. That mismatch is the check.

5. **D5.** Before the gate: both timers appear in `systemctl list-timers` with a future next
   elapse. After deletion: neither unit is known to systemd, no `*.service`/`*.timer` for either
   name exists under `/etc/systemd/system`, and brief 2's drift check is green with the dated
   exclusion entries removed rather than left expired.

6. **The demonstrated-red pass of criterion 14**, run once per new assertion.

**The constraint that governs every assertion here.** A negative rule is asserted by **absence
of capability**, never by performing the action. Nothing in this brief sends anything, pushes a
vault `main`, enables a disabled timer to see what happens, or reaches for `--no-verify`. The
checks are about state: a file that exists, a list that matches a manifest, a unit that systemd
no longer knows. If you find yourself doing the thing to see whether it is blocked, stop.

**Never weaken a check to get green.** Not `bin/verify.sh`, not the new suite, not brief 2's
drift check, not `tests/test_phaseb_brief_jobs.sh`. If a check goes red during this work, the
input is wrong.

## Out of scope / do not touch

- **The W5 row at `design/open-decisions.md:871`.** Brief 3 owns that edit
  (`.claude/briefs/workflow-coverage-checker.md:93-96`). Check whether it has landed; do not
  make it a second time from here.
- **Making ops mode record episodic memory.** `bin/agent_propose.sh:236,368-372` skips it by
  design (NUC-36). Criterion 3 records the consequence; changing it is a separate decision.
- **Renaming or bumping the cost.log schema.** `schema=3` has readers at
  `bin/run_record.sh:37`, `tests/test_scorecard.sh:36-40` and `tests/test_buzz_adapters.sh:203`.
  If the owner needs a column, add one; do not renumber the schema as a convenience.
- **`~/.local/bin/hermes`, `~/.hermes/profiles/` and the profile configs.** Brief 5 explicitly
  leaves them alive and hands the `AGENT_PROFILE` defect here
  (`.claude/briefs/hermes-kanban-retirement.md:267-271`). W1 *uses* those directories; it does
  not restructure them.
- **`bin/consolidate_memory.sh`.** Its discovery glob (`:149`) already does the right thing.
  Adding an explicit persona list to it would replace a working discovery with a hand-maintained
  roster — the exact defect W3 exists to remove.
- **Codegen of `--allowedTools`, or any runtime read of `design/`.** D4 chose (b) and gave the
  reason (`design/open-decisions.md:347-352`); `bin/deploy:20` makes the runtime read impossible
  anyway.
- **`config/job-overrides/archive/`, `profiles/archive/`.** History.
- **`bin/local_tier_eval.sh`'s captured fixtures.** `:45-60` deliberately captures inputs once
  so every model is graded on byte-identical data. W3 changes where its unit list comes from; it
  must not change what a captured fixture contains mid-eval, or the score is graded against a
  moving input.
- **Notion.** The two campaign pages stay. Nothing here deletes, archives or edits them — the
  broker refuses archiving anyway (`~/CLAUDE.md` § the Notion broker), and the pages are the
  campaigns' only surviving artifact.
- **The other four `/etc`-only units.** `fleet-turn-check.{service,timer}` and the rest are
  brief 2's backport, not this brief's deletion.

## Notes / preconditions

**BLOCKER — the D5 half cannot execute before 2026-09-04 01:30, and no agent may move that
date.** Read from the units themselves, 2026-09-02:
`praetorium-content-strategy-research.timer` carries four absolute `OnCalendar` lines ending
`2026-09-03 23:00`; `praetorium-faceless-content-research.timer` ends `2026-09-04 01:30`. Both
are the make-up schedule for the four nights lost to the 2026-08-27 OAuth outage, and
`Persistent=true` does not re-fire a slot that fired and failed — **a night deleted early is
lost permanently.** Write the W1–W4 half now; do not touch `/etc` until the last run has
completed and been counted.

**Confirm completion from the producer's own counter, not from the clock.**
`~/agent-workforce/var/notion_research_pages.json` read 2026-09-02 05:25 CEST:
`content-strategy-2026` `run_count = 5`, `faceless-content-product` `run_count = 5`, last runs
`2026-09-01 21:05 UTC` and `2026-09-01 23:36 UTC`. Two firings remain each, so both should
reach **7**. D5 recorded 4 each on 2026-09-01 and projected 7 — that projection is on track,
and 7 against a `--total-runs` default of 6 (`bin/notion_research_page.py:147`) is the known,
harmless overshoot from the 08-31 hand-run that the make-up schedule never deducted
(`design/open-decisions.md:456-458`). Record it; do not treat it as a defect and do not delete a
night to make the arithmetic tidy. If either counter is below 7 when you arrive, a run failed —
stop and report rather than deleting the unit.

**This brief's own scaffolding is on the cleanup list, and the recursion is real.** Brief 2
hands the `praetorium-phaseb-brief@*` units here (`.claude/briefs/deploy-drift-check.md:259-266`):
all six exist in **both** `systemd/` and `/etc` (`d72f562`), byte-identical, and all five timers
have now fired — `@6` at 2026-09-02 05:22, which is the run that wrote this file. Three things
follow. **(a)** They are `spent` (`design/agent-model.md:184`), so removal is correct. **(b)**
Removal must be from **both** trees in one change — `/etc`-only leaves them source-only, which
is brief 2's defect in the other direction. **(c)** `tests/test_phaseb_brief_jobs.sh:79-80`
asserts each unit is installed in `/etc` and byte-identical to source, and `:26-29` asserts the
queue holds exactly ids `{2,3,4,5,6}`; that suite must be retired **in the same commit** as the
units, or `bin/verify.sh` goes red on a deliberate deletion. Retiring a suite alongside the
thing it guards is correct; retiring it to get past a red is not, and the difference is whether
the guarded thing still exists.

**Other measured facts, 2026-09-02:**

- The four hermes persona stores W1 needs already exist: `~/.hermes/profiles/{marcus,claudius,
  augustus,trajan}/memories`. `aurelian` has none and needs none — he owns zero workflows
  (`design/agents/aurelian.toml`, 0 `[[workflows]]`).
- Persona-named profiles already work end to end, which is the positive control for W1:
  cost.log shows `augustus augustus-content fallback` (33 runs) and
  `claudius bd-stall-radar recorded` (19). The mechanism is fine; only the key is wrong.
- The manifests hold 26 `[[workflows]]` entries — marcus 4, claudius 6, augustus 4, trajan 12 —
  of which 22 `standing`, 2 `campaign`, 2 `dormant`. Twelve carry a `profile`. Re-measure
  before relying on any of these; the D5 half changes two of them.
- `design/` is not deployed (`bin/deploy:20`); `~/agent-workforce/design` does not exist.
- `bin/verify.sh` already collects every `tests/*.sh`, so a new suite is picked up with no gate
  change.
- **Commit each coherent piece immediately.** `agent-workforce-auto-sync.timer` fires every 15
  minutes and commits any dirty tree with `git add -A` under a generic message; work left
  uncommitted is swept into a commit that describes something else. For the D5 half, that
  matters more than usual — the deletion and the manifest transition must land together or the
  tree briefly declares a unit that no longer exists.
