# Open decisions — the sync agenda before Phase B

**Status:** open, 2026-09-01. This is the single list. D1 is closed; D2 and D3 each end in
a decisions section, and this file consolidates what is still unanswered plus the work D1
decided in principle but never implemented.

**How to use it:** answer inline in CAPS under each item, the same way D1 §7 was closed.
That worked — the answers stayed attached to the evidence instead of living in a chat
scrollback. Nothing in Phase B starts until D1–D9 are answered.

---

## Where each session landed

| | Doc | Decisions | State |
|---|---|---|---|
| D1 | `workflow-registry.md` | 8 | **all closed** 2026-09-01 (`ed568f8`) |
| D2 | `agent-model.md` §8 | 5 open + 1 withdrawn | open |
| D3 | `eval-spec.md` §8 | 4 | open |

D1 also left **four work items decided in principle and not done** (W1–W4 below). They are
not questions; they are the backlog D1 handed forward.

---

## The nine open decisions

### D1 — Deny the outward connectors in `~/.claude/settings.json`
*(D2 §8.1)*

Gmail `send_message`, M365 `outlook_send_mail`, Drive `share_file` and Figma are live in
every Buzz agent session, on a box whose charter is "no email, no social, no messaging
humans from this box — it holds no outward credentials, ever." The charter is true about
*credentials* and false about *tools*: `claude-agent-acp` sets
`settingSources: ["user","project","local"]` and agents run with cwd `/home/dave`, so
`~/.claude/settings.json` governs all five. Its deny-list covers the four secret paths and
Notion, and nothing else.

- **Cost:** one deny line each. Nothing the fleet uses today.
- **Catch:** one settings file governs *your own interactive sessions here too*. A split
  policy needs a wrapper injecting `--settings`.
- **Recommend:** yes. The mechanism is proven — the Notion deny dropped tools mid-session.

**ANSWER (2026-09-01): DENY ALL FOUR, AND SPLIT THE POLICY — agents strict, Dave open.**

Measured across **479 transcripts, the box's entire history**, before deciding:

| connector | tool schemas | invocations, ever |
|---|---|---|
| Figma | 33 | **0** |
| Microsoft 365 | 41 | 8 — *all reads* |
| Gmail | 29 | **0** |
| Google Drive | 11 | **0** |

The 8 M365 calls were `sharepoint_search` x3 + `read_resource` x4 (2026-08-03) and one
`outlook_calendar_search` (2026-08-09). **No outward action has ever been invoked from this
box** — no `send_message`, no `outlook_send_mail`, no `share_file`, not once. Method note: the
first run of this measurement globbed `*/*.jsonl`, matched **zero files**, and returned a clean
`0` for every connector. A count over a path that does not exist is not evidence of absence —
assert the corpus is non-empty first, and keep a positive control (`mcp__qmd__*`, 85 calls) in
the same query.

**`permissions.deny` removes the tool definition from the prompt, not just the call.** Proven
in the same corpus: Notion, denied 2026-08-03, contributes **0** definitions to today's
transcripts, while undenied Figma contributes 198-495 each. So this pays twice — it closes the
charter gap *and* drops **114 tool schemas** from every request on a fleet where marcus is
actively failing `Prompt is too long` x258 as the 20-channel DAG root.

**Capability loss is zero, because no capability this box depends on lives in the
`mcp__claude_ai_*` namespace.** Notion is the worked control: denied 08-03, and the
`buzz-notion-broker` was built for augustus on **08-10, seven days later, and works**. The two
real paths are untouched — 7 `notion_*` tools via `buzz-team-mcp.py` -> `buzz-notion-broker.py`
(`--user` unit, active since 08-17) for Buzz agents, and five REST helpers (`notion_rest.py`,
`notion_daily.py`, `notion_research_page.py`, `notion_markdown.py`, `notion_content_migrate.py`)
for scheduled jobs. The deny is what *enforces* the standing Notion-REST-only directive.
Figma has never been called here and Figma work is Mac-side. M365/Gmail/Drive were tools without
credentials — and could never serve a scheduled job anyway (zero MCP, 9/9 runners verified), so
a real calendar fix has to be a scoped REST helper regardless.

**General rule this establishes:** a capability this box depends on lives in a script or a
broker it owns, never in an account-level OAuth connector. Connectors cannot reach the scheduled
surface, cannot carry policy, and cannot be scoped per-agent.

**Split policy — the obvious implementation is a silent no-op; use `CLAUDE_CODE_EXECUTABLE`.**
Read from the installed `claude-agent-acp` 0.64.0:

- `dist/acp-agent.js:4156` sets `settingSources: ["user","project","local"]` on the real session
  query, so `~/.claude/settings.json` **does** govern agent sessions. (`dist/index.js:47`'s
  `settingSources: []` is unrelated — it reads the managed-policy tier only, to hoist env vars.)
- **`--settings` in `BUZZ_ACP_AGENT_ARGS` would have been accepted and ignored.** `index.js`
  parses only `--version`/`-v` from argv; caller options arrive over ACP `_meta` as
  `userProvidedOptions`. The flag would have looked configured and done nothing — the same
  class as every "config edit is inert until the process reloads it" trap in `~/CLAUDE.md`.
- The working seam is **`CLAUDE_CODE_EXECUTABLE`** (read 3x in `acp-agent.js`, alongside
  `pathToClaudeCodeExecutable`): point it at a wrapper that execs the real `claude` with
  `--settings <strict file>` appended. `claude --help` confirms `--settings <file-or-json>` and
  that it is an *additional* source ("managed settings and --settings still apply"), so deny
  lists union — a `--settings` file can only tighten, never loosen.
- Rejected `CLAUDE_CONFIG_DIR` (the other candidate seam): it relocates credentials, projects
  and the shared file-memory pool at `~/.claude/projects/-home-dave/memory/` that all four
  agents and Dave's own sessions deliberately share. Too wide.

Resulting shape:

- `~/.claude/settings.json` — unchanged. Keeps the 10 secret-path denies and
  `mcp__claude_ai_Notion` (the REST-only directive binds Dave too). Dave's interactive box
  sessions keep Gmail/M365/Drive/Figma.
- `~/.config/buzz-team/agent-settings.json` — new strict file, a **superset**: every deny above
  plus `mcp__claude_ai_Gmail`, `mcp__claude_ai_Microsoft_365`, `mcp__claude_ai_Google_Drive`,
  `mcp__claude_ai_Figma`. Written as a superset so it is correct whether `--settings` merges or
  replaces.
- `~/.config/buzz-team/claude-agent-wrapper.sh` — `exec claude --settings <strict> "$@"`.
- `buzz-agent@.service` — `Environment="CLAUDE_CODE_EXECUTABLE=%h/.config/buzz-team/claude-agent-wrapper.sh"`.

**Accepted cost, and its mitigation:** this creates a second policy file that can drift from the
first — the exact class D8 exists to catch, now sitting in the security layer. Mitigate inside
the D4(b)/D8 suite with one assertion: `agent-settings.deny` must be a **superset** of
`settings.deny`. A deny added to the base file and not the strict file is then a red gate, not a
silent hole. Verify the split the way `check-loaded.sh` verifies a `.env` — by what the running
process loaded, not by what the file says.

---

### D2 — Fix the alert throttle now, or fold it into a Phase-B brief?
*(D2 §8.3, covering §6.2 and §6.3)*

§6.2: the failure-alert throttle has been deployed-but-unwired for 18 days. `bin/deploy`
copied the script; nobody wrote `/etc`. 19 of the last 60 alert lines are the same
`qmd-refresh` message. §6.3: three repo unit files are *behind* `/etc`, and four live units
have no repo source at all.

- **Recommend:** fix §6.2 now — it is degrading alerting today. Fold §6.3 into Phase B.
- §6.6 (per-workflow locks) and §6.7 (import the four orphan units) are Phase B either way.

**ANSWER (2026-09-01): FIX BOTH NOW — the throttle is wired, and alert coverage is closed.**

Done and verified on the box, not merely committed.

**The throttle (§6.2) is live.** `/etc/systemd/system/agent-alert@.service` now execs
`bin/agent_alert.sh %i` instead of the inline `/bin/sh -c`. Proven end-to-end with a
throwaway failing unit through the real chain: two failures produced two records in
`~/logs/agent-alert.log` — the second reading
`[notification throttled: failure 1 since the last alert]` — and exactly **one** outbound
delivery, receipt `2026-09-01T14:12:04Z`, `discord_result: ok`, `buzz_result: ok`,
`outcome: delivered`. Two records, one notification, which is the design.

**Two corrections to the framing this decision was written on.**

1. *The alert volume was not chronic noise.* 27 alerts across 11 units in seven days
   looked like a standing duplication problem. It was **one incident**: headless Claude
   Code's OAuth session expired ~08-27 and every scheduled job failed identically with
   `Failed to authenticate: OAuth session expired and could not be refreshed` until Dave
   re-authorised on 08-31 ~11:40. Alerts stop dead at 11:42 and there have been none
   since. The daily counts (08-28:8, 08-29:5, 08-30:5, 08-31:6) read as ongoing only
   because nobody noticed 08-31's stopped mid-morning — presence is not freshness.
   The throttle would still have helped, collapsing ~27 alerts into ~11 first-failures;
   it just was not fixing what the doc said it was fixing.

2. *`fleet-eval` is deliberately unrouted and stays that way.* `systemctl --failed`
   named it, and the obvious reading — an eval harness that fails silently — is wrong.
   Its own header says `NO OnFailure=`, deliberately: it exits 1 on a regression and
   `--deliver` already posts the scorecard to `#ops`, so wiring the alert path would
   give one problem two notifications on different surfaces. Verified rather than
   assumed: this morning's `probe/p2_publish_approve` regression **was** delivered at
   `05:09:04Z`, discord ok, buzz ok, outcome delivered. Its non-zero exit is the intended
   quiet second signal and clears on the next green run. The receipt gap 08-16 → 09-01 is
   fourteen clean days, not fourteen lost alerts.

**Alert coverage (the genuine half).** Four units had no route and no one delivering on
their behalf: `local-tier-eval`, `memory-consolidation`, `scorecard` (whose
`ExecStartPost=deliver_scorecard.sh` only runs when `ExecStart` succeeded, so a failing
run delivered nothing at all), and `ttm-pool-drain` — which was untracked in `/etc`
entirely and is now adopted into `systemd/`. All four carry `OnFailure=agent-alert@%n.service`
in repo and `/etc`, in sync, confirmed live via `systemctl show`.

**Sequencing constraint, now recorded in `systemd/ttm-pool-drain.service`'s header.**
That unit fires **every two minutes**. Wiring its `OnFailure=` before the throttle existed
would have emitted ~720 notifications a day into Discord and Buzz. So the throttle is not
an independent improvement to alerting — it is a **precondition for widening alert
coverage at all**, and the two halves of this decision had to be done in that order.

**§6.3 re-measured, and it was right.** Three repo unit sources still differ from `/etc`
(`bd-stall-radar`, `m1-signal-scan`, `weekly-pre-assembly`) and — filtering Ubuntu stock —
three box units still have no repo source (`fleet-turn-check`,
`praetorium-content-strategy-research`, `praetorium-faceless-content-research`, plus their
timers). The doc said four orphans; `ttm-pool-drain` was the fourth and is now adopted.
**Both remain Phase B**, as recommended — but note `fleet-turn-check` is among the orphans,
and it is the gate that proves an agent can complete a turn.

**Two defects this surfaced, not fixed here, for the Phase-B list.**
- *The runner's stderr is captured but unfindable.* `agent_propose.sh:309` writes every
  attempt to `logs/agent_run.log` — untimestamped and interleaved with report prose from
  every job. The journal shows only `FAIL: runtime failed after 2 attempts`; finding the
  four-word cause of a four-day outage meant grepping 547 KB. Per-job, timestamped runner
  logs would have made this a ten-second question.
- *`Persistent=true` does not re-fire a slot that fired and failed.* Four nights of
  research runs were recovered only because someone hand-wrote four make-up `OnCalendar`
  lines. An unattended job that fails during an absence is not recovered by its own
  schedule, and nothing distinguishes "did not run" from "ran and produced nothing".

Commit: `28eda21` (unit sources) + this file.

---

### D3 — Skills posture
*(D2 §8.4)*

S1 and S2 have no skill index at all; the vault's 32 `08_skills/*/SKILL.md` are reachable
only by path, i.e. only if an agent remembers they exist. S3/Hermes has the only real index
(148 files), and `disabled` removes zero allowlisted skills on all four profiles.

Options, not exclusive: (a) leave it — agents read the vault and it works; (b) register the
role-relevant vault skills as Claude Code skills so they are *offered* rather than
remembered; (c) retire the S3 allowlist investment now that hermes is a one-off queue.

- **Recommend:** (b) for the four skills the content and research workflows actually name.
  Leave (c) until a card actually fails.

**ANSWER:**

---

### D4 — Is the manifest the source of truth?
*(D2 §8.5)*

i.e. may Phase B generate each wrapper's `--allowedTools` from `design/agents/*.toml`
rather than the reverse. This is the load-bearing one: it decides whether the manifests are
documentation or configuration. Everything in D3's coverage checker assumes the former is
false.

- **Recommend:** yes.

**ANSWER (2026-09-01): BINDING, CHECKED — option (b) of three.**

Not a yes/no. Measured before deciding: nine `run_*_cc.sh` runners carry `--allowedTools`,
collapsing to **four** distinct literals, a clean 2x2 of {may edit vault} x {may reach web}:

| set | tools | runners |
|---|---|---|
| vault-writer | `Bash,Read,Write,Edit,Glob,Grep` | bd_followup_drafts, knowledge_digest, raw_ingest |
| vault-writer+web | + `WebSearch,WebFetch` | m1_signal_scan, standing_research |
| reporter | `Bash,Read,Write,Glob,Grep` | daily_rhythm, overnight_morning_report, weekly_pre_assembly |
| reporter+web | + `WebSearch,WebFetch` | standing_research_topic |

The three postures were (a) documentation, (b) binding and checked by a test, (c) binding and
generated by codegen. **(b) chosen.** Runners keep their literal `--allowedTools`; a suite
under `tests/` asserts runner == manifest and fails `bin/verify.sh` on drift.

Rejected (c) — codegen — for a specific reason: `bin/deploy` performs **zero** codegen today
(measured, grep count 0); it is a pure copy. This box's demonstrated failure mode all week has
been *source and deployed disagreeing* (D2 §6.2 an 18-day unwired throttle, §6.3 repo units
behind `/etc`, §6.7 four live units with no repo source). Generation would have to emit into
both trees or it adds a **third** copy of the truth to a system already losing track of two,
and a generated runner cannot be hand-patched during an incident.

Rejected (a) — documentation — because it rots exactly the way this registry's own next-elapse
values did: wrong by *day* for three workflows, unnoticed until D2 read `systemctl cat`. And
D6's coverage checker would then be grading a fiction.

**Consequence — this merges D4 and D8 into one mechanism.** The check reads a runner file and
compares it against the manifest. Run the same check against the **deployed** tree
(`~/agent-workforce/bin/`) and it is D8's source-vs-deployed drift assertion, unchanged. One
suite, two invocations. Build it once.

**Tool profiles: NO — per-workflow literals, not four named profiles.** Every workflow spells
out its own list; no indirection to follow, and a one-off exception needs no new profile name.

Two schema consequences that follow, and are not optional:

1. **`tools` must move from `[surfaces.*]` to `[[workflows]]`.** It sits at surface level in all
   five manifests today, which is already lossy — the scheduled surface holds four distinct sets,
   and `claudius.toml:25` carries a `tools_web = [...]  # standing-research + m1 only` side-key
   precisely because one surface-level list could not express two workflows. That hack dissolves.
2. **A workflow with no model runtime must declare that explicitly**, e.g. `tools = "none"` with
   `runner_kind = "shell"`. Trajan's 12 workflows are plain shell/systemd jobs and correctly carry
   no `--allowedTools`. If absence is implicit, a runner that *loses* its tools line reads
   identically to one that never had one — the same silent-absence class as the empty `Synced At`
   column and the `Result=success` reset default. The check must be able to fail on a missing
   declaration, which means the declaration has to exist.

---

### D5 — Do you want a *standing* content-research workflow?
*(D2 §8.6 — replaces the withdrawn timer-fix decision)*

The two campaigns end 09-03 and 09-04 having delivered ~8 runs each on two named topics.
A permanent version is a different thing: it needs topic rotation, a slot that is not 01:30
(the `augustus-content` lock collision of §6.6), and its own registry row.

- **Recommend:** no for now. Let them expire; revisit when the content pipeline's existing
  backlog is consumed.

**ANSWER:**

---

### D6 — Build the workflow-coverage checker as the first Phase-B item?
*(D3 §8.1)*

9 of 26 workflows have a suite that owns them. Nothing on the box can report that, because
no layer knows the workflow list — the manifests are the first artifact that does. The
checker reads `design/agents/*.toml`, resolves each live workflow to a suite, and fails on
an unowned one.

- **Depends on:** W5 (explicit per-workflow `status`), and on D4 being yes.
- **Recommend:** yes. It is small, and it grades every brief that comes after it.

**ANSWER (2026-09-01): YES — but with a DECLARED join, not an inferred one. The premise above is wrong.**

The sentence "resolves each live workflow to a suite" has no implementation that works. Four
join rules were measured against the live tree; all four disagree, in both directions:

| join rule | covered | failure |
|---|---|---|
| unit name appears in suite text | 17 | **false green** — `agent-workforce-auto-sync` "covered" by a `list-timers` *fixture string* in `test_local_tier_eval_score.sh` |
| suite filename ~= unit name | 7 | false red on `augustus-content`, `agent-proposal`, `qmd-refresh`, `memory-consolidation` |
| manifest `runner` field | 7 | false red on **both** rhythm jobs: manifest records `run_daily_rhythm_cc.sh`, the suites name the wrappers |
| `runner` + resolve wrapper chain | 9 | right answer, wrong mechanism — credits daily-plan with `eod_summary_smoke` and vice versa, because they *share* an implementation |

Two structural reasons no rule can be made to work:

1. **13 of 26 entries carry no `runner`** (every trajan platform job), so that key is
   unavailable for half the registry.
2. **Coverage can sit three hops out.** `agent-inbox-sync` -> `bin/agent_inbox_pipeline.sh` ->
   `bin/agent_inbox_notion_sync.py` -> `test_agent_inbox_body_sync.sh`. Following one wrapper
   level is not enough, and following N levels is what produces the shared-implementation
   false green above.

**Decision: add `suite = [...]` to every manifest entry, hand-declared, and have the checker
read it.** Same shape as W5's `status` — it converts an inference problem into a data problem,
which is why the count stops moving. The checker asserts, per entry:

- `status == "standing"` and `in_repo != false` => `len(suite) >= 1`
- every path named in `suite` exists on disk
- every `tests/test_*.sh` is claimed by >= 1 entry (**orphan detection**, the reverse direction)

**Out-of-repo workflows are exempt but never invisible.** Three standing workflows exec
scripts that are not in this repo — `fleet-turn-check` (`~/.config/buzz-team/`),
`ttm-pool-drain` (`/usr/local/bin/`, root-owned) and `buzz-pr-watch` (`~/.local/bin/`, a
`--user` unit). They carry `in_repo = false` (the field D2 already added to ttm-pool-drain)
and are exempt from needing a suite, but the checker **prints them as a named list on every
run**. Exempt, not hidden — `fleet-turn-check` is the gate that proves an agent can complete
a turn, and it is exactly the kind of thing that disappears from a whitelist.

**The recorded figure was wrong three ways.** "9 of 26" in the headline, 11 implied by this
doc's own table (which lists 15 uncovered), and **16 covered / 10 uncovered** on measurement.
Corrected in `design/eval-spec.md` §8.1 in the same commit. The measured mapping, which the
`suite` fields are seeded from so Phase B does not re-derive it:

| workflow | suite(s) | found via |
|---|---|---|
| augustus-content | `run_content_via_buzz` | runner |
| content-change-dispatch | `content_change_dispatch`, `content_dispatch_state_hold` | name |
| knowledge-digest | `knowledge_digest_smoke` | name + runner |
| agent-proposal | `standing_research_smoke` | runner only |
| raw-ingest | `raw_ingest_smoke` | name + runner |
| bd-followup-drafts | `bd_followup_drafts_smoke` | name (owns a **dormant** unit) |
| praetorium-daily-plan | `daily_plan_smoke` | wrapper, not the recorded runner |
| praetorium-eod-summary | `eod_summary_smoke` | wrapper, not the recorded runner |
| weekly-pre-assembly | `weekly_pre_assembly_smoke` | name |
| fleet-eval | `fleet_eval` | name |
| local-tier-eval | `local_tier_eval_score` | name |
| scorecard | `scorecard` | name |
| memory-consolidation | `consolidate_memory` | ExecStart script |
| qmd-refresh | `vault_sync_guard` | ExecStart script |
| agent-inbox-sync | `agent_inbox_body_sync`, `agent_inbox_branch_rows` | **hop 3** |
| inbox-backlog-alert | `buzz_adapters` | ExecStart script |

Uncovered — 10, of which 2 campaign + 1 dormant (`bd-stall-radar`) + 7 standing. Of the 7
standing, 3 are `in_repo = false` (above) and **4 are writable today**: `m1-signal-scan`,
`overnight-morning-report`, `agent-workforce-auto-sync`, `overnight-pre-snapshot`. The
checker therefore ships **red with 4 named failures**, deliberately — those four are the
Phase-B backlog it exists to produce. `overnight-morning-report` is the sharp one: it is
uncovered and it is the unit carrying the entire recurring reporting-defect class.

One live orphan in the reverse direction: `tests/test_content_inbox_finalize.sh` owns
`content-inbox-finalize`, a unit **removed 2026-09-01** (units in `systemd/archive/`, nothing
in `/etc`). `bin/content_inbox_finalize.py` is still present and still gated. The orphan check
is what would have caught that on the day of the removal.

- **Depends on:** W5 (done, `3a52d42`), D4 (yes, `b49606b`).
- **Sequencing:** the `suite` + `in_repo` fields land now as a W-item (manifest data, same
  class as W5). The checker script itself is the first Phase-B brief.

---

### D7 — Leave the Hermes kanban surface unevaluated?
*(D3 §8.2)*

Nothing grades a kanban card's execution. This may be correct — but it should be a decision
rather than an omission.

- **Recommend:** yes, leave it; fold into D3 (skills posture) rather than answering twice.

**ANSWER:**

---

### D8 — Add a source-vs-deployed drift assertion to `bin/verify.sh`?
*(D3 §8.3)*

`verify.sh` grades the source tree; every other eval layer grades the deployed one. So a
green gate says nothing about what is running. **Two of D2's eight gaps were exactly this
defect** (§6.2 throttle, §6.3 unit drift).

- **Recommend:** yes. Highest-yield single check available.

**ANSWER:**

---

### D9 — Negative tests for `enforced = true` must-not rules?
*(D3 §8.4)*

The manifests carry 22 must-not rules; only some are `enforced = true`. An unenforced rule
is prose, and prose is what D2 §6.1 found sitting between the fleet and a live
`send_message`. A negative test fails if the mechanism is removed.

- **Depends on:** D1 — the deny-list is the mechanism these tests would assert.
- **Recommend:** yes, scoped to the outward-action rules only.

**ANSWER:**

---

## Carried work — decided in principle, not done

Not questions. D1 settled the direction; nobody has implemented them.

| | Item | Source | Note |
|---|---|---|---|
| W1 | Episodic memory keys on the OWNER persona, not the runtime profile name | D1 §6.2, §6.6 | No scheduled persona workflow accumulates episodic memory today. Fleet-wide rename, six jobs. |
| W2 | Every persona workflow's profile states its owner in one standard header line | D1 §6.3 | daily-plan/eod say "You are Marcus"; the `_cc_task` variants are persona-less. |
| W3 | Generate the reporting jobs' unit lists from the registry | D1 §6.4 | The `praetorium-*` glob defect exists in six files; 8 timers are invisible to every report. |
| W4 | Consolidate the two job-override example homes | D1 §6.5 | Stale directory archived 2026-09-01; the consolidation itself is not done. |
| W5 | Every workflow entry carries an explicit `status` | D3 §5 R15 | Manifest edit, not code. Blocks D6. |

---

## Suggested order

Dependencies first, then yield.

1. **D4** — decides whether the manifests are configuration. Everything downstream assumes it.
2. **D1** — closes a live outward-action exposure and unblocks D9.
3. **D2** (§6.2 half) — stops the alert degradation running today.
4. **W5 → D6** — makes coverage self-reporting instead of a number that rots.
5. **D8** — the drift assertion; retires the class that produced two of D2's gaps.
6. **D3 + D7 together** — one skills-and-kanban conversation, not two.
7. **D5**, then **D9**, then **W1–W4** as Phase-B briefs.

Items 1–3 are conversations. 4–7 are briefs.
