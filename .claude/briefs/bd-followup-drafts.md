# Brief: BD follow-up draft pack (`bd-followup-drafts`)
**Date:** 2026-07-30   **Verify:** `bash bin/verify.sh` (from `~/dev/agent-workforce`)

## The manual activity this replaces

Source: Notion task block *"AI Agent Workforce — one revenue-leverage block"*
(`3a98d768-1ede-81d6-ae19-d86797287cc2`, 2026-07-30 13:00–15:00, Notes: *"improve at most one
workflow tied to sales, content or client delivery. No infrastructure work without a named
business bottleneck."*).

**Named business bottleneck — evidenced, not inferred.** Dave hand-writes every BD follow-up
message, one at a time, re-loading context each time (who, last substantive exchange, the ask,
NL/EN, channel). Empirically it does not happen. From his own vault:

- `07_daily/logs/2026-07-22`: *"Three overdue BD sends — all three still sit `Planned` in the
  Task Inbox: Isaac Griffith (5d late) · Joost thank-you (5d late) · DP World named-intro ask
  (2d late). Loop #5 in its cheapest possible form — three short messages, none sent for five
  days."*
- Same log, efficiency review: *"the same three BD messages have been re-surfaced and
  re-carried for 5+ days without being sent."*
- `bd-stall-radar` (nightly, Sun–Thu 23:00) already flags the deals and **stops at flagging**:
  *"each is a candidate for one concrete re-engagement touch"* — the drafting is Dave's.

**The missing artifact is the text, not the decision and not the task row.** All three overdue
sends already existed as `Planned` Notion Task Inbox rows with due dates for the full five days.
Adding more task rows demonstrably does not close this loop; a copy-paste-ready message at 06:00
does. Revenue link is direct: Priority 1 is *"BD / sales activation — revenue is the binding
constraint on post-Qredits runway"*, and `open_loops#5 Conversation-to-Deal Conversion` is the
standing loop this feeds.

**Approach (user-confirmed):** draft for **all Dave-owed next actions** — the union of
bd-stall-radar stalls, Client Pipeline rows with a passed `Next action date`, and open BD-tagged
Notion Task Inbox items. Radar-stalls-only was rejected: the evidenced failures were task rows,
not radar stalls.

## Acceptance criteria

A new scheduled job `bd-followup-drafts` runs headless Claude Code (Opus 5) Sun–Thu 23:30 under
`bin/agent_propose.sh`, and:

1. **Produces one dated pack** `_inbox/agents/YYYY-MM-DD_bd-followup-drafts.md` containing up to
   **5** ready-to-send drafts, or emits an explicit `DECLINE:` sentinel when nothing is owed.
   Enforced by `AGENT_VERIFY_CMD='…/proposal_or_decline.sh bd-followup-drafts'` — a dead run can
   never log as a clean NOPROPOSAL.
2. **Input set** = union of three sources, de-duplicated by deal:
   - the previous night's `_inbox/agents/<date>_bd-stall-radar.md` (if present);
   - Client Pipeline (data source `e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e`) rows whose
     `Next action date` has passed;
   - Notion Task Inbox (data source `4dbb4389-6c4a-4f57-b70f-10d899483c21`) rows that are not
     Done/Cancelled, are BD-scoped (`Client` relation non-empty **or** `Area`/`Track` names BD),
     and whose `Due date` is today or earlier.
3. **Suppression guard (reuse bd-stall-radar's, verbatim in spirit):** never draft for `Stage`
   = `Closed` or `On Hold`; never draft for a track `04_operations/current_priorities.md` marks
   parked or counterparty-owned (e.g. The Cold Hub *"no touch before September"*, DP World
   *"none owed — keep warm"*).
4. **No elapsed-time claims — the make-or-break rule.** No draft may assert silence,
   non-response, or elapsed time (*"I haven't heard back"*, *"it's been three weeks"*,
   *"following up since we spoke on X"*). Pipeline `Last contact` is known-unreliable: ProActive
   read 82d when the real touch was 6d; four consecutive EOD wraps (07-24 → 07-28) wrongly
   called the Rhenus connect undone; the 07-29 log calls it *"the third instance of this failure
   mode this week"* — outbound email and LinkedIn leave no trace on this box. Ground each draft
   in the last **substantive, evidenced** exchange from the vault (`07_daily/logs/`,
   `current_priorities.md`, `open_loops.md`). Where the record is ambiguous, emit a
   `⚠ Unverified:` line above the draft naming what could not be confirmed — never a confident
   opener. Same principle as `vault_sync_guard.sh`: a loud refusal beats a confident wrong
   artifact.
5. **Every draft closes on a concrete ask** — a named next step with a date and/or named people.
   Never *"let's stay in touch"* (`open_loops#5`; restated in `current_priorities.md` §Priority 1
   for ProActive, Rhenus and DP World).
6. **Locale-correct:** draft in the language of the row's `Locale` (`nl` | `en`). Dutch rows get
   Dutch drafts.
7. **Channel-correct:** `Email` present → email draft with a subject line; otherwise LinkedIn.
   A LinkedIn *connection note* draft must be ≤300 characters; a DM to an existing connection may
   be longer. Each draft states its channel and, for LinkedIn notes, its character count.
8. **Carry-forward de-dup:** if the previous pack already drafted for a deal and nothing about
   that deal changed, do not re-emit an identical draft — list it as
   `carried (unchanged from <date>)`. Prevents a daily nag file.
9. **Ranked** by revenue proximity: `Stage` Proposal/Active > Qualified > Prospect, then by how
   overdue. The 5-draft cap applies after ranking, and anything dropped by the cap is named in a
   one-line tail (no silent truncation).
10. **Never acts outward and never writes Notion.** Reads only. Pipeline state changes stay
    Dave's call from the Mac — identical to `bd_stall_radar_task.md` step 3.
11. **The pack reaches Dave.** `ExecStartPost=bin/deliver_report.sh` with
    `REPORT_DIR`/`REPORT_GLOB`/`REPORT_SUBJECT` set per-unit, so the pack posts to Discord
    (fail-soft, 26h staleness guard). No new delivery code.
12. **The gate is green:** `bash bin/verify.sh` passes — `bash -n` + `shellcheck -S error` clean
    over every `bin/` shell script, and every `tests/*.sh` exits 0, including the new smoke test.

## Files to create

- **`bin/run_bd_followup_drafts_cc.sh`** — the "brain" `agent_propose.sh` execs. Model on
  `bin/run_knowledge_digest_cc.sh` exactly:
  `CLAUDE_BIN` (default `/home/linuxbrew/.linuxbrew/bin/claude`), `GUARD` (`VAULT_SYNC_GUARD`
  override), `INBOX` (`BD_FOLLOWUP_INBOX` override, default `$HOME/agent-worktrees/inbox`),
  `TASK_FILE` (`BD_FOLLOWUP_TASK` override, default
  `$HOME/agent-workforce/profiles/bd_followup_drafts_cc_task.md`). Unreadable task file → exit 1.
  `"$GUARD" check` fails → print `REFUSING` + why, exit 1 **without launching the agent** (a
  draft built off a frozen mirror asserts stale facts to a real client). Then
  `cd "$INBOX"` and `exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" --model claude-opus-5
  --permission-mode bypassPermissions --strict-mcp-config --mcp-config '{"mcpServers":{}}'
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep"`.
  **Pin `claude-opus-5`, not the `opus` alias** (an alias silently rolls forward).
  **No `WebSearch`/`WebFetch`** — drafts must be grounded in the vault + Notion, never the open
  web, and the box holds no outward tool.

- **`profiles/bd_followup_drafts_cc_task.md`** — the task profile; it *is* the mechanism, so it
  must state acceptance criteria 2–10 explicitly (the smoke test greps for them). Structure it
  like `profiles/bd_stall_radar_task.md`:
  - STEP 0 — read the previous pack in `_inbox/agents/` for carry-forward de-dup.
  - Notion reads via REST **only** — the MCP is removed box-wide; token loaded on the same shell
    line (`set -a; source ~/.config/agent-workforce/secrets.env; set +a`), `Notion-Version:
    2025-09-03`, `POST /v1/data_sources/{id}/query`. On `"object":"error"` note it and continue —
    never retry in a loop or hang.
  - Vault context via `qmd get` on known paths (`04_operations/current_priorities.md`,
    `05_knowledge/open_loops.md`) — path-based `get`, not the slow semantic `query`. The inbox
    worktree does not contain `04_operations/`.
  - Voice: Dave's, per the vault voice profile — demonstrate the mechanism (cause→effect), no
    aphorisms, no invented figures (`feedback_no_business_case_numbers`), operator register.
  - Per-draft output block: **Deal · Channel · Locale · Why now (evidenced, with source) ·
    ⚠ Unverified (if any) · THE DRAFT (verbatim, copy-paste-ready) · The ask**.
  - Front-matter `target: none — send material, not a vault change` so this pack is never
    promoted into the vault by `agent_inbox.py`.
  - `DECLINE: no Dave-owed BD next action today` sentinel when the input set is empty after
    suppression.
  - Hard boundary restated: never email, post, DM or message anyone; never write Notion.

- **`profiles/bd_followup_drafts.env.example`** — mirrors `profiles/knowledge_digest.env.example`
  (header stating EXAMPLE ONLY, live file at `~/.config/agent-workforce/bd_followup_drafts.env`
  mode 600, outside git):
  `AGENT_PROFILE=claude-opus`, `AGENT_TASK_SLUG=bd-followup-drafts`, `AGENT_MAX_ATTEMPTS=2`,
  `AGENT_RUNTIME_CMD='~/agent-workforce/bin/run_bd_followup_drafts_cc.sh'`,
  `AGENT_VERIFY_CMD='~/agent-workforce/bin/proposal_or_decline.sh bd-followup-drafts'`.

- **`systemd/bd-followup-drafts.service`** — copy `bd-stall-radar.service`, plus
  `After=network-online.target qmd-mcp.service bd-stall-radar.service`,
  `Environment=AGENT_JOB_OVERRIDES=/home/dave/.config/agent-workforce/bd_followup_drafts.env`,
  `ExecStart=/home/dave/agent-workforce/bin/agent_propose.sh`, and
  `ExecStartPost=/home/dave/agent-workforce/bin/deliver_report.sh` with
  `Environment=REPORT_DIR=/home/dave/agent-worktrees/inbox/_inbox/agents`,
  `REPORT_GLOB=*_bd-followup-drafts.md`, `REPORT_SUBJECT=[Praetorium] BD follow-up drafts`.

- **`systemd/bd-followup-drafts.timer`** — `OnCalendar=Sun,Mon,Tue,Wed,Thu 23:30`,
  `RandomizedDelaySec=3min`, `Persistent=true`, `WantedBy=timers.target`. Comment the two
  reasons: it mirrors `bd-stall-radar`'s Sun–Thu cadence so each pack lands for a Mon–Fri
  morning and consumes that night's fresh radar output; and 23:30 clears the 04:30 / 05:30 /
  06:00 morning jobs that share `agent_propose.sh`'s global `flock` on `/tmp/agent_propose.lock`
  (a collision there is a **silent** `SKIP: previous run still active`).

- **`tests/test_bd_followup_drafts_smoke.sh`** — offline by contract, sourcing
  `tests/rhythm_test_lib.sh`; model on `tests/test_knowledge_digest_smoke.sh`. See test plan.

## Files to modify

- **`CLAUDE.md`** — new subsection under the research/rhythm job docs describing
  `bd-followup-drafts.timer` (Sun–Thu 23:30), and the two rules that are easy to get wrong:
  (a) **no draft asserts elapsed time or silence** — `Last contact` is known-unreliable because
  outbound email/LinkedIn leaves no trace on this box; (b) **drafts are send-material, not vault
  changes** — the pack is never promoted, and the job never writes Notion pipeline state.
- **`docs/runbook.md` § Job wiring** — add a table row:
  `| BD follow-up drafts | **Sun–Thu 23:30** | bd-followup-drafts.{service,timer} |
  ~/.config/agent-workforce/bd_followup_drafts.env | profiles/bd_followup_drafts_cc_task.md |
  *(headless Claude Code)* |`, and one paragraph on why it is chained after the radar.

## Test plan

`tests/test_bd_followup_drafts_smoke.sh` — offline: throwaway git fixtures + `make_mock_claude`,
never `~/vault`, never a real remote, never a live Notion call.

1. **Wiring** — `env.example` parses: `AGENT_TASK_SLUG=bd-followup-drafts`,
   `AGENT_PROFILE=claude-opus`, `AGENT_RUNTIME_CMD` resolves to an executable script and names
   `run_bd_followup_drafts_cc.sh`, `AGENT_VERIFY_CMD` wires
   `proposal_or_decline.sh bd-followup-drafts`, and no hermes/OpenRouter runtime survives.
2. **Freshness refusal** — on a `stale_behind` fixture the runner exits non-zero, logs
   `REFUSING`, and **never launches the agent** (`claude_argv.log` absent).
3. **Clean run** — on `clean_current` the runner exits 0; `claude_argv.log` contains `claude-opus-5`
   as an exact line (catches an `opus` alias regression), `--strict-mcp-config` + `mcpServers`,
   the task prompt, and **no** `WebSearch|WebFetch`.
4. **The task profile encodes the mechanism** (grep assertions, one per rule — this is what makes
   the gate meaningful for this feature):
   - all three input sources: `_bd-stall-radar.md`, `e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e`,
     `4dbb4389-6c4a-4f57-b70f-10d899483c21`;
   - the Stage guard names both `Closed` and `On Hold`;
   - the **no-elapsed-time-claim** rule is present and names the `Last contact` unreliability;
   - the `⚠ Unverified` escape hatch is defined;
   - the concrete-ask rule is present and explicitly rejects *"let's stay in touch"*;
   - the `Locale` nl/en switch;
   - channel selection + the LinkedIn 300-character connection-note budget;
   - the 5-draft cap **and** the no-silent-truncation tail;
   - carry-forward de-dup against the previous pack;
   - `never write` Notion + never act outward;
   - the `DECLINE:` sentinel contract;
   - REST-only Notion (asserts no `mcp__notion` / `notion-query-data-sources` reference).
5. **Units** — service sets `AGENT_JOB_OVERRIDES` to `bd_followup_drafts.env`, `ExecStart` is
   `agent_propose.sh`, `ExecStartPost` is `deliver_report.sh` with `REPORT_GLOB` matching
   `*_bd-followup-drafts.md`; timer is `Sun,Mon,Tue,Wed,Thu 23:30` with `Persistent=true`.

`bash bin/verify.sh` runs this test plus `bash -n` + `shellcheck -S error` over the new runner.

## Out of scope / do not touch

- **Cold first-touch outreach** for the ~60 screened-but-never-contacted Client Pipeline rows.
  Deliberately deferred: colder, and it drags in `Consented at` / `Chain status` consent and
  non-compete screening as a hard gate. Different, larger machine.
- **`bin/bd_stall_radar_kernel.py` and `profiles/bd_stall_radar_task.md`** — leave them alone.
  The radar stays deterministic and $0; this job *consumes* its output. Do not fold drafting into
  it.
- **Any Notion write** — no page creation, no property updates, no Box Output registration
  (`8869d761-…` is a promotion registry for canonised artifacts, not a draft inbox).
- **The 12 approved-but-not-promoted inbox backlog** — a separate cleanup, not this feature.
- **Sending anything.** The box holds no outward credential and never will. Drafts only.
- `vault-boxsafe` `main`, `publish_boxsafe.sh`, `~/agent-workforce/` (deployed tree — edit source
  and run `bin/deploy`).

## Notes / preconditions

- **Verified present:** `bin/agent_propose.sh` (runtime-agnostic, execs `AGENT_RUNTIME_CMD`,
  owns worktree/write-boundary/commit/metrics), `bin/proposal_or_decline.sh`,
  `bin/vault_sync_guard.sh`, `bin/deliver_report.sh` (parameterised via
  `REPORT_DIR`/`REPORT_GLOB`/`REPORT_SUBJECT`), `tests/rhythm_test_lib.sh` with
  `make_vault_fixture` / `make_mock_claude` / `env_value` / `assert`.
- **Notion access verified live today (2026-07-30)** with `NOTION_API_TOKEN` from
  `~/.config/agent-workforce/secrets.env`: Client Pipeline `e5b6fe9a-…` (80 rows, schema
  includes `Stage`, `Locale`, `Email`, `Next action date`, `Days since last contact`,
  `Decision-maker`, `Trigger event`, `Notes`, `Chain status`) and Task Inbox `4dbb4389-…`
  (100 rows; open BD examples today: *"Follow-up check: Barry Stegeman (DACHSER) — reply on
  LinkedIn"* and *"Follow-up check: Rob van Dijk (Broekman)"*, both due 2026-07-30 with a
  `Client` relation). REST is the **only** Notion path on this box — never reach for any
  `mcp__…Notion` tool.
- **`agent_propose.sh` still requires `OPENROUTER_API_KEY` to be set** (preflight gate at
  `bin/agent_propose.sh:168`) even though the runtime is Claude Code. It is present in
  `secrets.env`; do not remove that gate.
- **The live env file is outside git.** `/implement` should install it:
  `install -m 600 profiles/bd_followup_drafts.env.example
  ~/.config/agent-workforce/bd_followup_drafts.env` — and must never `git add` from that path.
- **Nothing deploys automatically.** After the gate is green: `bin/deploy` (rsync + atomic
  rename, additive; `--dry-run` first), then
  `sudo systemctl enable --now bd-followup-drafts.timer`. Source edits alone leave systemd on
  the old code.
- **`agent-workforce-auto-sync.timer` fires every 15 min** (`git add -A` → commit → push to
  `origin/main`). Commit this work **immediately** after editing or the message is lost to a
  generic `Auto-sync:` commit with unrelated WIP riding along. Also `git fetch origin` and diff
  the checked-out branch against `origin/main` before committing — local checkouts here can be
  silently merged-and-stale.
- **First run is Sun 2026-08-02 23:30.** To validate sooner without waiting:
  `sudo systemctl start bd-followup-drafts.service` and read the pack in
  `~/agent-worktrees/inbox/_inbox/agents/`. Expect a real pack — the two DACHSER/Broekman
  follow-up checks are due today and ProActive's Isaac nudge is planned for 07-30.
