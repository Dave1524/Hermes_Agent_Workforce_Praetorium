# Brief: Retire the Hermes kanban surface (S3)
**Date:** 2026-09-02   **Verify:** `bash bin/verify.sh` from the repo root (syntax + shellcheck -S error over `bin/`, then every `tests/*.sh`)

This is Phase-B brief 5. It executes the retirement sequence recorded in
`design/open-decisions.md` D7 (line 577), in the order recorded there.

**It ships green, and that is a warning rather than a reassurance.** Every other Phase-B brief
leaves a new assertion red on arrival; this one deletes mechanisms and the tests that covered
them, so `bin/verify.sh` is green before you start and must be green when you stop. Nothing in
the gate will tell you the retirement actually happened. The evidence is live measurement — a
stopped unit, a board exported, a runtime tree with the script gone — plus one deliberate
red-then-green step named in the Test plan. Do not treat a green gate as the deliverable.

**Step 1 is a human action and it is not done.** See Notes / preconditions before anything else.

## Acceptance criteria

1. **The 5 blocked SEO cards are somewhere durable before any other step begins.** They are the
   only content on the board that is not a completed record; they have never dispatched (all 5
   carry no `started_at`, measured 2026-09-02) and they have been blocked since 2026-07-10.
   **Moving them is Dave's action on the `vpc-seo` work, not this brief's and not any agent's.**
   The brief sequences it and stops. Criterion 3 is blocked until this is confirmed done —
   confirmed by Dave saying so, not by an agent inspecting a destination and inferring it.
2. **All 11 cards exist as a plain record outside the board**, taken while the gateway is still
   running, and **that record does not land in this repo unless it is content-free.**
   `Dave1524/Hermes_Agent_Workforce_Praetorium` is a **public** GitHub repo — verified 2026-09-02
   by an unauthenticated `GET /repos/...` returning 200 with `"private": false` — and
   `agent-workforce-auto-sync.timer` pushes any dirty tree to it within 15 minutes. D7 step 2
   names `design/archive/` as the destination; taken literally that publishes 11 card bodies of
   client and vault-derived content to the open internet. Destination is a blocker (Notes).
3. **`hermes-gateway.service` is disabled and stopped, and still installed.** One review cycle,
   reversible, per D7 step 3. It is a `--user` unit
   (`~/.config/systemd/user/hermes-gateway.service`, linked from
   `~/.config/systemd/user/default.target.wants/hermes-gateway.service` since 2026-07-07), so it
   needs a session that can reach the user bus — see Notes.
4. **No live scheduled job resolves to `bin/kanban_run_and_wait.sh`, and this is proven from
   journals rather than asserted.** Eleven units select their runtime through
   `AGENT_JOB_OVERRIDES` env files under `~/.config/agent-workforce/`, which are deny-listed and
   must not be read. Each unit's journal logs `run attempt N/M: <command>` — the *effective*
   `AGENT_RUNTIME_CMD` — which is the method `design/workflow-registry.md:176` already
   records for exactly this question. Prove it before deleting anything.
5. **The dead code is gone from source and from the deployed runtime.** Source:
   `bin/kanban_run_and_wait.sh`, `bin/agent_propose.sh:267-270`. Runtime:
   `~/agent-workforce/bin/kanban_run_and_wait.sh` still exists (7,599 B, 2026-08-12) and
   `bin/deploy` is additive by default — deleting from source alone leaves the runtime holding
   the script.
6. **`tests/test_agent_propose_smoke.sh` scenario 11 is removed in the same commit as
   `bin/agent_propose.sh:267-270`.** D7's dead-code list misses it.
   `tests/test_agent_propose_smoke.sh:213-224` asserts the kanban path-match de-stack
   (`FAIL: runtime failed after 1 attempts` for a `run_cmd` containing
   `kanban_run_and_wait.sh`). Delete the case block without it and the smoke suite goes red —
   which would make this brief ship red, contradicting its own premise. This is the one place
   the gate can catch you, and the Test plan's red-then-green step is how you use it.
7. **Both kanban suites are deleted with the code, in the same commit** —
   `tests/test_kanban_run_and_wait.sh` and `tests/test_kanban_crash_not_benign.sh`. They pass
   today and prove nothing; D7 names them as the first two orphans found under D6's
   reachability rule. No manifest `suite = [...]` field references either
   (verified 2026-09-02 by grep over `design/`), so nothing else breaks — but if brief 3's
   coverage checker has landed and *declared* a subject for either file, that declaration goes
   in the same commit. A declaration naming a deleted path is precisely what brief 3's
   "declares missing path" check fires on.
8. **trajan's `"schedule recurring work on hermes cron"` `must_not` rule is removed, together
   with its `test_exempt` string, and no test replaces it.** The rule is **moot, not standing.**
   A standing rule is one a mechanism still holds; this one's stated mechanism is the
   non-existence of a surface (`design/agents/trajan.toml:220-224`), and once the retirement
   lands there is no cron host, no gateway and no board — nothing whose removal a test could
   detect, and any test pinning an empty cron list goes red the day the surface is gone. This
   is what the exemption itself predicted; the exemption must not outlive the thing it
   exempted. `tests/test_fleet_guards.sh:209-218` requires each `enforced = true` rule to name
   a `test` **or** a `test_exempt`, so removing rule and exemption together is clean and
   removing only one is not.
9. **trajan's `"unblock a vpc-seo card without Dave"` rule does not silently keep pointing at a
   surface that no longer exists** (`design/agents/trajan.toml`, `enforced = false`). Its
   subject leaves with criterion 1's card move: either remove it with the board, or re-point it
   at wherever the SEO queue now lives. Which one depends on the criterion-1 destination, so it
   resolves after the blocker clears, not before.
10. **Every manifest's `[surfaces.kanban]` block records the surface as retired-with-date, not
    deleted.** Five blocks: `marcus.toml:41`, `claudius.toml:34`, `augustus.toml:42`,
    `trajan.toml:29`, `aurelian.toml:39` (aurelian's is already `present = false`).
    No `[[workflows]]` entry anywhere carries `surface = "kanban"` (verified 2026-09-02), so no
    workflow is orphaned by this and no `suite` field moves.
11. **The design docs stop describing S3 as live.** `design/agent-model.md:41` (§2 surface
    table), `:63-72` (the S3 skill-index passage), `:108` and `:114` (schema enum and the
    `skills` field), `:471` (§8 decision 4c); `design/eval-spec.md:199` (gate-ownership row),
    `:234-237` (§7.2), `:283-284` (§8 decision 2); `design/workflow-registry.md:128-142` (§5)
    and `:193-196` (§7.6). §5 and §7.6 are the sharpest case: they adopted *"recurring work =
    systemd timers, queued one-offs = kanban"* and *"vpc-seo stays"* on 2026-09-01, the same day
    D7 concluded retire. A reader hitting §5 first gets the opposite instruction. Correct it in
    place with the date and the reason, the way `open-decisions.md:16-18` requires — a design
    doc carrying two contradicting measurements of the same thing is worse than one carrying
    neither.
12. **`design/agent-model.md:20-33` still makes its argument after the edit.** That passage's
    whole point is that claudius is *four* different things and no file names them together —
    it is the finding the document exists for (§1). Retirement makes it three. Record the
    retirement without deleting the argument, and do not renumber S4.
13. **The measured skills counts are not relocated to a place where they are false.** D7 step 5
    says to fold the measured 25 "into the S1/S2 discussion where it is actually true".
    **It is not true there.** `design/agent-model.md:58` states plainly that S1 and S2 have no
    skill index and that `~/.claude/skills/` does not exist; the 46/44/25/23 counts are
    `~/.hermes/shared-skills/` offerings resolved per hermes *profile* (`:63-70`). The hermes
    profiles outlive the board (criterion 14). So the `skills` field either states what it
    actually measures — the hermes profile's offered set — or leaves the schema, with the
    counts landing somewhere they stay true. Do not carry the number into an S1/S2 claim.
14. **Nothing that merely shares the `hermes` name is touched.** `~/.local/bin/hermes` (the CLI)
    is load-bearing: `bin/local_tier_eval.sh:105` execs it as
    `timeout "${TIMEOUT_MIN}m" "$HERMES" -t "$toolset" -z "$prompt" -p marcus -m "$model"`, and
    `local-tier-eval` is a standing platform job firing six times a day
    (`design/agents/trajan.toml:78-84`). `-p marcus` names a hermes profile directory, so
    `~/.hermes/profiles/` and the configs `bin/apply_skills_allowlist.sh` writes are reachable
    from a live job and are **not** S3-only. `local-tier-eval` must pass on its first firing
    after the gateway stops, and that firing must be observed, not assumed.
15. **`bash bin/verify.sh` exits 0 at the end, and its state was recorded before you started.**
    Brief 2's drift check and brief 3's coverage checker both ship red and may already have
    landed. A pre-existing red is not this brief's to fix, and it must not be mistaken for one
    this brief caused — record the failing suite names first, and compare sets at the end.
16. **`bin/praetorium-status.sh` stops reporting two retired surfaces as health.** Its
    "User services (hermes-gateway)" block (`:22-30`) will print `active=inactive
    enabled=disabled` forever, and its "Hermes cron (last run)" block (`:31-49`) queries a host
    that `design/workflow-registry.md:126-127` already declared retired on 2026-09-01. No test
    asserts either block. A status view that reports a retired surface every run trains its
    reader to skip it.

## Files to create

- **`design/archive/`** — does not exist today. Created by criterion 2, and **only** if the
  board record that goes in it is content-free (ids, status, assignee, board, timestamps,
  `skills`), because this repo is public. The full record — titles, bodies, results — goes
  outside the repo; `~/OUTBOX/` exists and is the obvious home. **Do not decide this alone**:
  it is a blocker in Notes.

  Whatever lands in `design/archive/` should be enough to answer "what did S3 ever do" without
  quoting a card: 11 cards, 6 `done` / 5 `blocked`, assignees trajan 5 / augustus 4 /
  claudius 2, created 2026-07-10 → 2026-07-20, last completion 2026-07-20, 0 of 11 with a
  non-empty `skills` field. All measured 2026-09-02.

No other file is created. This brief is subtraction.

## Files to modify

- **`bin/agent_propose.sh`** — delete the `case "$run_cmd"` block at `267-270` and its NUC-38
  comment at `264-266`; `max_attempts` then defaults to 3 for every path.
  **Leave `DEDUP_EXIT=3` (`:256`) and `CRASH_EXIT=4` (`:263`) and all their handling
  (`:271`, `:322-327`, `:338-343`, `:349-352`) alone.** They are an exit-code contract with the
  runtime, not kanban code: `bin/run_content_via_buzz.sh:40,48` produces exit 4 **today**
  (`crash() { log "CRASH: $*"; exit "$CRASH_EXIT"; }`), and `docs/runbook.md:88-90` documents
  that split as live. `DEDUP` has no producer left after this brief, but
  `~/agent-workforce/logs/cost.log` carries one historical `outcome=DEDUP` row
  (2026-08-13T01:33:57+02:00) that `bin/scorecard.sh:51-56` must still bucket correctly.
  What *is* wrong after the deletion is the attribution: `:257-262` credits
  `kanban_run_and_wait.sh` for the CRASH exit. Re-point it at the live producer. A boundary
  attributed to a thing that no longer exists is the §2/§6.1 defect D3 found — it survives the
  removal of whatever actually holds it.

- **`tests/test_agent_propose_smoke.sh`** — remove scenario 11 (`:213-224`). Renumbering the
  scenarios after it is optional and noisy; leaving the gap is fine.

- **`design/agents/trajan.toml`** — remove the `hermes cron` `[[must_not]]` (`:220-224`),
  resolve the `vpc-seo` rule per criterion 9, and mark `[surfaces.kanban]` (`:29-40`) retired.
  Its `notes` block currently reads *"This is the only surface where a skills allowlist does
  real work"* — which stops being true and, read together with criterion 14, was never the
  whole truth.

- **`design/agents/marcus.toml:41`, `claudius.toml:34`, `augustus.toml:42`,
  `aurelian.toml:39`** — the remaining `[surfaces.kanban]` blocks, per criterion 10.

- **`design/agent-model.md`** — `:28`, `:41`, `:63-72`, `:108`, `:114`, `:471`, per criteria
  11-13. `:471` is §8 decision 4(c) ("retire the S3 allowlist investment now that hermes is a
  one-off queue … leave (c) alone until a card actually fails"): record it as answered by
  retirement for the *offering* question, and explicitly not as licence to delete
  `bin/apply_skills_allowlist.sh`.

- **`design/eval-spec.md`** — `:199`, `:234-237`, `:283-284`. §7.2 is a gap that closes by the
  surface going away, not by an eval being built; say that, with the date.

- **`design/workflow-registry.md`** — `:126-142` (§5, both the `hermes cron` and `hermes
  kanban` bullets) and `:193-196` (§7.6's answer). Per criterion 11.

- **`design/open-decisions.md`** — D7's answer block already concludes RETIRE; record execution
  against the recorded sequence, in place.

- **`bin/overnight_pre_snapshot.sh`** — the "Gateway health" section (`:50-55`, running
  `hermes gateway status`) and the "Kanban state" section (`:57-62`, running
  `hermes kanban list --json`). Both are wrapped in `run_or_note` (`:15-20`), so they will not
  break the snapshot — they will quietly capture a dead surface every night at 04:25.

- **`profiles/overnight_morning_report_cc_task.md:25`** — instructs the morning-report agent to
  "run the same checks the pre-snapshot covers (kanban, …)". It must not keep asking for a
  kanban diff once the snapshot stops taking one.

- **`bin/praetorium-status.sh`** — `:22-30` and `:31-49`, per criterion 16.

- **`docs/runbook.md`** — `:74-80` explains `AGENT_MAX_ATTEMPTS=1` by reference to
  "`agent_propose.sh`'s path match", which this brief deletes, and `:79-80` tells an operator to
  **revert** augustus-content by restoring
  `config/job-overrides/archive/augustus-content.env.example` — whose `AGENT_RUNTIME_CMD`
  (`:6`) invokes `kanban_run_and_wait.sh`. After this brief that is an instruction to install a
  runtime that no longer exists. `:106` describes `AGENT_RUNTIME_CMD` as the
  "actual hermes / kanban invocation".

- **`config/job-overrides/README.md:30`** and **`profiles/standing_research.env.example:34`** —
  both name `kanban_run_and_wait.sh`; the second is already commented out. The README's mention
  is *historical* ("the kanban-dispatch era"), which stays accurate; the archived
  `.env.example` is history and stays as history. What must not survive is a **live**
  instruction pointing at either.

- **`CLAUDE.md:16`** — marcus's roster row reads "none — interactive + kanban owner".

## Test plan

**Nothing is red before this change, and that is the shape of the risk.** There is no failing
assertion to turn green; the gate cannot distinguish "retired correctly" from "not started".
So the plan is: pin the one place the gate *can* speak, then verify the rest live.

**The one red-then-green step.** Delete `bin/agent_propose.sh:267-270` **first**, alone, and run
`bash bin/verify.sh`. It must fail, in `tests/test_agent_propose_smoke.sh`, on
`FAIL after exactly 1 attempt (kanban de-stack)` (`:222`). That red is the proof scenario 11
was really covering the case block. Then remove scenario 11 and re-run to green, and commit
both together. If the first run is green, stop — you deleted something other than the block, or
the suite is not running.

Follow the suite conventions if you touch any test: `set -uo pipefail`, the `assert()` helper
that scopes `pipefail` **off** inside the condition, and the `yes | grep -q y` canary. Under
`pipefail` a condition fails a true assertion and silently passes a negated one, which is how
this gate certified nothing for a stretch in August (`CLAUDE.md` § Verification).

**Deletion safety — run before deleting, not after.**

1. `grep -rn "kanban_run_and_wait" .` over the repo, and confirm every remaining hit is prose
   or archive, not a live invocation.
2. Criterion 4's journal check across the eleven `AGENT_JOB_OVERRIDES` units: each `run attempt
   N/M: <command>` line names the effective runtime. **Do not read
   `~/.config/agent-workforce/*.env` to answer this** — deny-listed, and the journal answers it
   better anyway (a file can be stale; the journal is what ran).
3. `bin/deploy --dry-run --prune` and **read the output before running it for real.** `--prune`
   applies to every path in `PATHS` (`bin/deploy:20` — `bin profiles docs CLAUDE.md AGENTS.md
   README.md config systemd`), not just the file you meant. If the dry run names anything
   beyond `bin/kanban_run_and_wait.sh` and the doc/profile edits, **stop and report** — do not
   proceed and do not narrow the guard to make it quiet.
4. `tests/` is not in `bin/deploy`'s `PATHS`, so the two deleted suites need no deploy.
   `bin/verify.sh:47` globs `tests/*.sh`, so no gate edit is needed either.

**Live verification, separate from the gate:**

- The board export is taken **before** the gateway stops. `hermes kanban list --json` returned
  all 11 cards on 2026-09-02 from a shell with no user-bus access, so the read path is the CLI
  and its store rather than the gateway socket — but taking the export first means you never
  have to rely on that.
- After `systemctl --user disable --now hermes-gateway`: `is-active` = `inactive`,
  `is-enabled` = `disabled`, the `default.target.wants` symlink gone, and the unit file still
  on disk. The CPU burn and the repeating `ClientConnectorDNSError` against
  `gateway-us-east1-d.discord.gg` (D7: ~7,074 s since 2026-08-17, 53 unhealthy warnings in 30d)
  stop — check the journal is quiet, not just that the unit is down.
- **`local-tier-eval` must be observed passing on its first firing after the gateway stops**
  (02,08,11,14,17,20:17 — `design/agents/trajan.toml:82`). This is the criterion-14 control and
  the single most likely way this brief breaks something. Read the run's output; `active` and a
  next-elapse prove nothing (`design/eval-spec.md:184-186`).
- Normalise timestamps before building any timeline from these: the box's services log UTC
  while `journalctl` renders CEST (`~/CLAUDE.md` § Debugging the services on this box).

**One rule governs everything above: a negative rule is asserted by the absence of capability,
never by attempting the action.** Nothing in this brief creates a card, dispatches one,
unblocks one, or schedules a hermes cron job to see whether it is refused. The retirement is
proven by a stopped unit, an absent script and an empty grep.

## Out of scope / do not touch

- **`~/.local/bin/hermes`, `~/.hermes/profiles/`, and the episodic-memory path.** D7 is
  explicit, and criterion 14 gives the live reason. They are entangled with the
  `AGENT_PROFILE` naming defect (six scheduled jobs logging `memory=no-store`), which is
  `design/workflow-registry.md` §6.6 work and belongs to brief 6, not here.
- **`bin/apply_skills_allowlist.sh` and `docs/skills_allowlist.md`.** They edit and document
  `~/.hermes/profiles/<p>/config.yaml`, which a live platform job still reads. Whether the
  allowlist affects a `-z` oneshot is **unverified** — which is exactly why the script must not
  be deleted on the assumption that it is S3-only.
- **`bin/local_tier_eval.sh`.** Not one line. It is the reason the CLI stays.
- **The DEDUP/CRASHED exit-code contract** in `bin/agent_propose.sh`, `bin/scorecard.sh` and
  `bin/content_change_dispatch.sh:100-108`. Exit 4 has a live producer; exit 3 has a historical
  cost.log row. Removing either is a separate decision with its own evidence, and it is not
  this one.
- **`tests/test_agent_propose_smoke.sh` scenarios 10, 21 and 22.** They drive a *mocked* runtime
  (`run_scenario` at `:101-114` sets `MOCK_EXIT_CODE`), not `kanban_run_and_wait.sh`, so they
  survive its deletion and keep the exit-code contract covered. Leave them.
- **`hermes-gateway.service` itself — disable, do not delete.** One review cycle, per D7 step 3.
  Note it is one of the nine `~/.config/systemd/user/` units with no source counterpart in this
  repo (brief 2). Adopting it into `systemd/` is brief 2's call, not this brief's — and
  adopting a unit you are retiring would be the wrong direction anyway.
- **Archived cards.** Registry §5 records 33 + 3 stale cards `archive`d rather than purged on
  2026-09-01, and the `default` board deliberately kept. Nothing here purges anything; hermes'
  own `archive` is the reversible operation and `--rm` is not.
- **`profiles/archive/`, `config/job-overrides/archive/`, `docs/briefs/NUC-30-*.md`.** History.
  A retired mention in an archived file is a correct record, not drift.
- **D3 part 2 (pointer skills), W1-W4, D5's campaign-unit cleanup.** Briefs 4 and 6.
- **The `surface` enum's other values.** S1, S2 and S4 keep their identifiers; do not renumber
  after removing S3.

## Notes / preconditions

**BLOCKER 1 — the 5 SEO cards have not moved, and no agent may move them.** D7 step 1 is
unambiguous: *"Do not proceed to step 2 until they are somewhere durable."* Destination is the
`vpc-seo` work in the Vantage SEO remediation task list. This is Dave's action on the Mac. The
brief is written on the assumption it has **not** happened. Criteria 3 onward do not start
until Dave confirms it has. Confirmation means Dave says so — an agent inspecting a task list
and inferring a match is not confirmation.

Note the ordering is not ceremonial: the gateway dispatches `ready` cards every 60 s, so the 5
cards are safe only while they stay `blocked`, and once the gateway is disabled nothing can
dispatch them at all. Retiring first strands them; unblocking them to "clear" them dispatches
them. Neither is this brief's to do.

**BLOCKER 2 — where the board export goes is not settled, and the default is unsafe.** D7 step
2 says `design/archive/`. This repo is **public** — verified 2026-09-02 by an unauthenticated
`GET https://api.github.com/repos/Dave1524/Hermes_Agent_Workforce_Praetorium` returning 200 with
`"private": false` — and `agent-workforce-auto-sync.timer` commits and pushes any dirty tree
every 15 minutes under a generic message. Card titles and bodies are client and vault-derived
content. Options, for Dave: (a) full record to `~/OUTBOX/` (exists) and a content-free index in
`design/archive/`; (b) full record into the vault inbox, which is in-bubble; (c) content-free
only. **Do not resolve this by writing the cards into the repo and deciding afterwards** —
auto-sync makes that irreversible within 15 minutes.

This is worth stating even though it is out of D7's frame: D7's step 2 was written about
durability, and nothing in it is wrong about durability. The destination is a boundary
question that D7 did not ask.

**BLOCKER 3 — disabling the unit needs a user bus, and an agent session may not have one.**
`systemctl --user` from this session failed with *"Failed to connect to user scope bus via local
transport: $DBUS_SESSION_BUS_ADDRESS and $XDG_RUNTIME_DIR not defined"* (2026-09-02).
`bin/praetorium-status.sh:27` works around it with `XDG_RUNTIME_DIR="/run/user/$(id -u)"`, and
`bin/apply_skills_allowlist.sh:141` prints the same form. If the workaround does not work in
the session doing this, the disable is Dave's step from an interactive login — say so and stop,
rather than reaching for a stronger tool.

**Measured on the box 2026-09-02, and each of these is checkable:**

- `hermes kanban list --json` → 11 cards. 6 `done`, 5 `blocked`. Assignees: trajan 5,
  augustus 4, claudius 2. `created_at` spans 2026-07-10 → 2026-07-20; the 5 `blocked` cards
  have **no `started_at`** — they were never dispatched, consistent with the registry's finding
  that they were assigned to `engineer`, a profile not on disk
  (`design/workflow-registry.md:131-134`). Last completion 2026-07-20, i.e. 44 days idle.
- **0 of 11 cards carry a non-empty `skills` field** (every one is `[]`). This is the
  measurement that settles D3 (c) by fact rather than preference: the per-profile allowlist
  mechanism has never been exercised once from a card.
- `~/agent-workforce/bin/kanban_run_and_wait.sh` exists in the deployed tree, 7,599 B, mtime
  2026-08-12.
- `~/agent-workforce/logs/cost.log` holds exactly one `outcome=DEDUP` row and zero
  `outcome=CRASHED` rows across 308 lines.
- `hermes-gateway.service` is `WantedBy=default.target` with the symlink dated 2026-07-07;
  `ExecStart` is `…/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run`.

**Facts from D7 worth carrying, because a fresh measurement will not reproduce them:**

- The kanban dispatch path last actually ran 2026-08-13. `content-change-dispatch`'s timer is
  active and firing every 15 minutes and its journal shows the kanban runtime command — which
  looked like a live dependency and is not. Today's ticks short-circuit at
  `bin/content_change_dispatch.sh:71`, and the live `AGENT_RUNTIME_CMD` in the shared override
  is `run_content_via_buzz.sh` (`bin/content_change_dispatch.sh:25` and
  `systemd/augustus-content.service:11` point at the same file). **A green timer on a dead code
  path is a false signal of the same class as D8's** — do not re-derive "it is live" from that
  journal line.
- D7's own method note: a grep that matches only literal `hermes ` invocations under-reports
  every `$VAR` caller, and that is how `bin/local_tier_eval.sh` was first misclassified as a
  path-only reference. Re-run any such sweep for variable forms.
- Do not propagate the number 526 for non-Discord gateway log lines; it counts traceback frames
  of the same errors.

**Process:**

- Commit each coherent piece immediately. `agent-workforce-auto-sync.timer` fires every 15
  minutes and commits any dirty tree with `git add -A`; work left uncommitted gets swept into a
  message that describes something else. For a long batch, stop the timer first and restart it
  after.
- **Never reach for `--no-verify`.** It is a `must_not` rule in its own right
  (`design/agents/trajan.toml`), and nothing in this brief needs it.
- Record `bin/verify.sh`'s failing-suite set before you start (criterion 15). Briefs 2 and 3
  both ship red; their reds are not yours.
