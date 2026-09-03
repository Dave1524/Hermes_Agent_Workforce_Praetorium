# Brief: Finalise the agent harness on S1 — DMs, channels and forums

> ## STATE — 2026-09-03 10:04 CEST: all 20 criteria met; ships RED as designed
>
> Updated after a `/code-review` pass — 15 findings, all 15 verified real, all 15 acted on.
> The accounting below is post-fix. See "What the review changed" at the end of this banner.
>
> **`bash bin/verify.sh` exits 1.** That is criterion 20's expected outcome, and every finding
> is either pre-existing or this brief's own deploy drift. Nothing was softened to reach it.
>
> ### Every delta from brief 6's baseline, by name
>
> | Measure | Brief 6 | Now | Why |
> |---|---|---|---|
> | workflow entries parsed | 30 | **35** | the five `surface = "interactive"` entries (criterion 15) |
> | standing | 23 | **28** | same five |
> | own a suite | 16 | **22** | +5 interactive (`tests/test_buzz_interactive_harness.sh`), +1 `fleet-turn-check` |
> | exempt | 3 | **2** | `fleet-turn-check`'s `suite_exempt` removed — criterion 17 |
> | **uncovered** | **4** | **4** | **unchanged, same four names.** W6. Not this brief's |
> | distinct suite paths claimed | 24 | **26** | the two new suites |
> | suites on disk | 45 | **47** | the same two files |
> | unclaimed suites | 21 | 21 | unchanged |
> | orphaned suites | 1 | 1 | `tests/test_content_inbox_finalize.sh`. W12; widening the rule is its own brief |
> | executed `tests/*.sh` | 47 | **49** | the two new suites |
> | DRIFT findings | 2 | **9** | +6 `bin/`, +1 `buzz-team/` — this brief's own edits |
>
> **Read 22-of-28 with care.** The ratio improved because the *denominator* grew by five, not
> because the hole shrank. The hole is identical: `overnight-morning-report`, `m1-signal-scan`,
> `agent-workforce-auto-sync`, `overnight-pre-snapshot`. Four is the number to track.
>
> ### The 2 FAILs and 9 DRIFT lines, accounted for
>
> - **2 FAILs, both pre-existing and both W-rows this brief was forbidden to close.** W6's four
>   uncovered standing workflows; W12's one orphan suite.
> - **7 new DRIFT lines, all this brief's own edits**, and all cleared after merge by
>   `bin/deploy` (six) and `bin/deploy_buzz_team.sh` (one): `deploy_buzz_team.sh` (source-only,
>   new), content differs on `check_deploy_drift.sh`, `local_tier_eval.sh`,
>   `overnight_pre_snapshot.sh`, `praetorium-status.sh`, `verify.sh`, and — from the review pass
>   — `buzz-team/check-team-kinds.py`. This is the documented feature-branch condition;
>   deploying an unmerged branch to the live runtime is not this brief's to do.
> - **2 pre-existing DRIFT lines**, unchanged: `agent-drift-check.{service,timer}` need `sudo`.
> - **`buzz-team/` contributes exactly ONE drift finding, and it is a fix.** The adoption was
>   byte-identical — `bin/deploy_buzz_team.sh --dry-run` reported `live tree already current`
>   before the review pass, which is the convergence proof. The review then found a fail-open in
>   `check-team-kinds.py` (below), and repairing it is a source-side change that the drift check
>   correctly reports as `content differs` until the converge runs. That is the manifest's own
>   stated order — adopt what is live, *then* change it, so the first drift run reports a
>   difference somebody made on purpose. The three excluded files still show as
>   `info: box-only: … declared excluded`, never as drift.
> - **One FAIL appeared and was fixed properly, not around.** `tests/test_phaseb_brief_jobs.sh`
>   asserted `ids == {2,3,4,5,6}` — a frozen snapshot that went red the moment the queue gained
>   brief 7, i.e. on correct use. Replaced with what is actually invariant: ids unique and
>   contiguous from 2, and every `praetorium-phaseb-brief@N.timer` declared in the queue
>   (units → queue only; the reverse would require a systemd unit per queue entry, which is
>   backwards). All three failure modes demonstrated red.
>
> ### Deviations from the brief, recorded rather than silently taken
>
> 1. **Criterion 3's `Bearer ` literal.** A ban on the literal string would fail correct code —
>    `buzz-notion-broker.py` builds its header as `"Bearer " + token`. The assertion targets a
>    credential-shaped *value* (`Bearer [A-Za-z0-9_-]`) instead, which is what the criterion was
>    protecting. The broker is separately asserted to *read* its token rather than embed one.
> 2. **Criterion 14's route half is in the new suite, not `tests/test_fleet_guards.sh`.** That
>    suite is box-gated on three live paths; the aurelian route assertions are decidable from a
>    checkout, and putting them behind a box gate would have made them unreachable on a runner.
> 3. **`design/fleet-suites.toml` does NOT register `tests/test_buzz_interactive_harness.sh`.**
>    Five workflows claim it, so it is workflow-owned, and that file's own stated purpose is to
>    own suites *no workflow claims*. Registering it would have made it claimed twice.
> 4. **`profile_in_repo = false` is new schema**, added because criterion 15's entries broke
>    `tests/test_fleet_ownership.sh`'s owner-header check: the five S1 charters are deny-listed
>    box paths, so no `Owner:` line in them can be asserted from here. It is DECLARED, never
>    inferred from the path's shape — a heuristic would also swallow a typo'd repo path and turn
>    a genuinely missing profile into a silent pass. Documented in `agent-model.md` §4.
>
> ### Opened, not closed
>
> **W13** — `verify-fleet.sh` is now sourced here but runs nowhere in the gate; adoption made it
> reviewable, not assertable. **W14** — the five `buzz-agent@*` units carry no `OnFailure=`, and
> the reason that is a design question rather than a missing line is in the row.
>
>
> ### One machine-level FAIL found while closing the loop — NOT this brief's, and NOT caused by it
>
> `~/.config/buzz-team/verify-fleet.sh` exits 1 on `7/fresh-config augustus (newer than unit
> start: buzz-agent@.service)`. **augustus has been running a 15-day-stale unit config**: the
> unit file was last written `2026-09-01 18:51` and his process started `2026-08-17 09:38`. It
> predates this session by two days and nothing here touched that file — this branch changed no
> `~/.config/systemd/user/` path and restarted nothing, and `cmp` confirms all 18 adopted files
> are still byte-identical to the box.
>
> It is the "a config edit is inert until the process reloads it" trap in its plainest form, and
> the journal shows exactly why it went unnoticed: augustus logs nothing but relay pings and
> `accepted=true`, so a stale process looks identical to a current one. The remedy is
> `systemctl --user restart buzz-agent@augustus`, which **this brief is forbidden to do**.
> Dave's call; surfaced here rather than silently carried.

>
> ### What the review changed
>
> A `/code-review` pass returned 15 findings. Each was verified against the code before being
> acted on rather than taken at face value; all 15 held. Six were fail-opens — checks that were
> passing without checking, which is the expensive half of a flaky gate and the class this
> repo's `## Verification` note already names.
>
> **Fail-opens closed (a check that could not fail is not a check):**
>
> - **`buzz-team/check-team-kinds.py` read the kind off the UUID.** It scanned cells
>   right-to-left for the first number, and a UUID is 32 hex digits — so a TEAM.md row naming no
>   kind fell through to the UUID cell and "documented" the digit run that starts it. For any
>   UUID beginning `9` + a hex letter that is exactly `9`, the stream default, and the row passed
>   as agreeing. The `else None` branch was unreachable for the same reason, which is what hid
>   it. Now stopped at the UUID cell, with a distinct "row names no kind" finding. Proven both
>   ways against the box copy: old passes the fixture, new reports it.
> - **The `kind` column had no ground truth.** A closed vocabulary stops a third spelling, not
>   the wrong one of the two — and a row typed `timer` for a unit with no timer reproduces
>   exactly the defect the column exists to prevent. `tests/test_fleet_ownership.sh` now joins
>   every row against `systemd/**`, resolving both template shapes, and *names* the two
>   campaign units it cannot judge. A zero-row join is itself a failure — which the join had:
>   it read an unexported `REPO_ROOT` and silently fell back to cwd.
> - **`bin/check_deploy_drift.sh` never checked declarations for files in BOTH trees.** The
>   header claimed "an undeclared file in EITHER tree is red"; that held for each direction
>   separately and for neither together, so a file hand-copied into both passed `cmp` and was
>   reported by nothing. That is the likeliest shape of the bug, because copying is how such a
>   file arrives. Now red, in both the undeclared and the stale-exclusion form.
> - **`bin/deploy_buzz_team.sh` used manifest `path` values as unvalidated write destinations.**
>   A `../` component escapes the destination the guard above it just proved, and
>   `find -maxdepth 1 -printf '%f'` makes the result invisible in both membership directions.
>   Measured on a guard-stripped copy: `create   ../payload.toml`, `1 file(s) written.`, exit 0.
>   Now refused as a set, before any write.
> - **`tests/test_buzz_interactive_harness.sh` matched the DAG with a brittle regex.**
>   `author == "<hex>"` required exactly one space either side of `==` while the Python parser
>   uses `\s*`; a reformatted rule file would have made the negatives vacuous. Replaced with a
>   materialised admits map plus an assertion that it covers all five personas.
> - **The `list-timers` line in the three reporting profiles never worked.** Pre-existing, found
>   while fixing its neighbour: a system unit running as `dave` has no session bus, so a bare
>   `systemctl --user` exits 1. Both call sites now carry `XDG_RUNTIME_DIR`. Fixed together
>   under one-concept-every-site rather than left for the next reader to find twice.
>
> **Stale claims corrected, each with its method now stated:**
>
> - "**35 `governed_by` pointers led out of the repo**" was wrong under every method. Measured
>   at `a3bed90`: **5** `governed_by` values named the tree (one per persona manifest) and **56**
>   lines mentioned the path in any form. Both counts now carry the command that produced them,
>   in `design/agent-model.md` §2 and `design/phaseb-brief-queue.toml`.
> - "**47 executed `tests/*.sh`**" in `design/eval-spec.md` was the *pre*-brief-7 count carrying
>   a post-brief-7 date. `bin/verify.sh` globs `tests/*.sh` and runs all **49** — 47 `test_*.sh`
>   plus two helper libs exec'd as no-ops.
> - `design/fleet-suites.toml` still said "four columns" and "scope/status/owner agree" after the
>   column was added.
> - An eval-injection seam in `tests/test_fleet_ownership.sh` (a manifest-supplied path
>   interpolated into an `eval`'d condition) and a `--help` range in `bin/deploy_buzz_team.sh`
>   that ran past the header into code.
>
> **One thing the review surfaced that is deliberately NOT fixed here:** `config/` and
> `profiles/` are shipped by `bin/deploy` and compared by nothing. That is W7, pre-existing, and
> widening the drift check is its own brief.
>
> **Every fix carries its own assertion, and each was demonstrated red first.** Four new
> assertions in `tests/test_deploy_drift.sh` (traversal, both-trees, stale exclusion, and the
> respelled consumer check), five in `tests/test_buzz_interactive_harness.sh` for the kind
> checker — which `bin/verify.sh` called and nothing tested — and the kind join in
> `tests/test_fleet_ownership.sh`. The gate's S1 kinds step now prints its pass, because a
> silent check between a header and a `test:` line reads exactly like a step that stopped
> running.
>
> ### A second machine-level fail-open, observed while re-running the extra gate
>
> `~/.config/buzz-agents/check-loaded.sh` reports `OK  <name>  prompt is current with
> GUARDRAILS.md` for an agent whose `.prompt` **does not exist**. Its own stderr says so on the
> two lines immediately above the OK:
>
> ```
>   DEAD     praetorium unit has never started
> stat: cannot stat '.../praetorium.prompt': No such file or directory (os error 2)
> check-loaded.sh: line 41: ((: 1785495882 >  : arithmetic syntax error: operand expected
>   OK       praetorium prompt is current with GUARDRAILS.md
> ```
>
> The comparison's right-hand operand is empty, the `((` fails, and the failure is read as a
> pass — the same shape as the `pipefail`/`grep -q` trap this repo's `## Verification` note
> already documents, in a gate outside the repo. Two identities are affected (`praetorium`,
> `spike0`), both `DEAD`, so nothing is currently mis-certified as live.
>
> **Not this brief's, and not fixable from here.** W13 records why `check-loaded.sh` was not
> adopted: it reads the deny-listed `~/.config/buzz-agents/` tree by design, so this repo cannot
> hold a source for it. Reported from its own output rather than by reading the file. Dave's
> call, alongside the augustus restart above.
>
> ### Dave's action after merge
>
> `bin/deploy` (clears 6 drift lines) and `bin/deploy_buzz_team.sh` — **a separate script, not
> `bin/deploy`**. It has exactly one file to write: `check-team-kinds.py`, whose fail-open the
> review pass closed. That one is a checker, not a dispatch rule, so **no restart is needed for
> it** — but the general case is the opposite, and a rule-file change is inert until each agent
> is restarted **by hand**, one at a time, because a malformed filter expression crash-loops the
> unit rather than silently never matching. `docs/runbook.md` § S1 has the loop.

**Date:** 2026-09-03   **Verify:** `bash bin/verify.sh` from the repo root
(bash -n + `shellcheck -S error` over `bin/`, then `bin/check_deploy_drift.sh`, then every `tests/*.sh`)

**Queue position:** brief 7. `design/phaseb-brief-queue.toml` ends at brief 6; add this entry.
**Ships:** RED — see criterion 20 for the exact expected exit and why it is not this brief's to clear.

---

## Why this brief exists

Phase B built a harness for the **scheduled** surface and only for it. `design/agent-model.md` §2
names four execution surfaces; every mechanism Phase B produced lands on **S2 (scheduled headless
Claude Code)** and on trajan's platform jobs. **S1 — Buzz interactive, which is every DM, every
channel message and every forum thread — got the descriptive half and none of the enforcing half.**

Measured on the live box 2026-09-03, not read from this repo's own docs:

1. **S1's governing files have no source in this repo.** `~/.config/buzz-team/` is a **fifth**
   governance tree. It holds the five dispatch-rule `.toml` files (the loop-guardrail DAG),
   `agent-settings.json` (the connector deny-list), `claude-agent-wrapper.sh` (the seam that makes
   that deny-list reach an agent), `buzz-acp-launch.sh` (the unit's actual `ExecStart`), the MCP
   bridge, the Notion broker and the fleet's own verification gate.
   `bin/check_deploy_drift.sh` compares four trees. **This is not one of them.** Every reference to
   it in `design/` is a `governed_by` pointer *out* of the repo — 35 such pointers across
   `design/agents/*.toml`, `design/agent-model.md`, `design/eval-spec.md`, `docs/runbook.md`.
   This is verbatim the finding that produced brief 2, one tree over: *"buzz-agent@.service is in
   that unsourced tree AND was edited on 2026-09-01 by brief 1. The fleet's core unit has no source
   of truth."* Brief 2 adopted the nine `--user` units and closed it. It did not adopt the files
   those units **read**, so the unit is now sourced and its entire configuration is not.

2. **S1 carries zero `[[workflows]]` entries.** All 26 entries across the five manifests are
   `platform` (16), `scheduled` (12) or `buzz_dispatch` (2). Zero are `interactive`. So
   `tests/test_workflow_coverage.py`'s `standing-has-suite` rule, the `status` vocabulary, the
   `suite` requirement and the contract layer are **structurally blind to every DM, channel post
   and forum thread on this box**. Nothing is failing; nothing is looking.

3. **The S1 gate already exists and is unowned.** `~/.config/buzz-team/verify-fleet.sh` (14,892 B)
   runs roughly twelve gates over exactly this surface — rules files, sandbox deny-paths, charter
   resolution, config freshness, kind agreement, broker reachability, env knobs, roster,
   calibration. It is **not in this repo, not in `bin/verify.sh`, and not in CI.**
   `design/eval-spec.md:53` files it as a "machine-level sibling outside this repo". A gate nobody's
   PR runs is a gate that drifts, and it is the only thing standing between the DAG and a cascade.

The user's framing is the correct one: the harness was never meant to cover only the automated work.
S2 is where the *jobs* run; S1 is where the *agents* are. Today the jobs are governed and the agents
are documented.

---

## The one design decision, already taken

**Adopt the mechanism; leave the prose.** Chosen 2026-09-03.

- **Mechanism** — a file read by a **process** (buzz-acp, `claude`, python, bash). It has a
  parseable shape, a wrong version has a mechanical symptom, and a reviewer can diff it. **Adopted
  into the repo.**
- **Prose** — a file read by an **agent** as instruction. Its correctness is judgement, it is the
  class most likely to accrete client detail, and `Dave1524/Hermes_Agent_Workforce_Praetorium` is a
  **public** repo that `agent-workforce-auto-sync.timer` pushes within 15 minutes. **Stays
  machine-level.**

State that rule in the declaration file so the next file lands on the right side without a new
decision. Three files sit on the prose side and all three are deliberate:
`TEAM.md`, `heartbeat.prompt`, `aurelian-calibration.md`.

I checked `TEAM.md` for client content and found none, and its six channel UUIDs are already in
`bin/buzz_routes.env` here — so this split is **not** a leak finding. It is a standing-risk
boundary, and the excluded files must be **declared excluded**, never merely absent (an absence
cannot be told from a deletion).

---

## Acceptance criteria

### A — Adopt the S1 mechanism tree

1. `buzz-team/` exists at the repo root and contains, **byte-identical to `~/.config/buzz-team/`
   at adoption time**, exactly these files:
   `marcus.toml`, `claudius.toml`, `augustus.toml`, `trajan.toml`, `aurelian.toml`,
   `agent-settings.json`, `claude-agent-wrapper.sh`, `buzz-acp-launch.sh`, `buzz-team-mcp.py`,
   `buzz-notion-broker.py`, `check-rules.py`, `check-team-kinds.py`, `notion-probe.py`,
   `verify-fleet.sh`, `fleet-turn-check.sh`, `context-cost.py`, `trace-turn.sh`, `watch-test.sh`.
   Byte-identity is asserted, not assumed — copy, then `cmp` every file, and fail the adoption if
   any differs. **Adopt what is live, then change it; never adopt a corrected copy**, or the first
   drift run reports a difference nobody made.

2. `buzz-team/MANIFEST.toml` declares **both** sets — adopted and excluded — with the
   mechanism-vs-prose rule stated in prose, and the reason each excluded file is excluded.
   `backups/` is declared excluded as runtime state.
   An excluded file must be named. Absence is not a declaration.

3. No adopted file carries key material. Asserted by the suite, not by inspection:
   no `nsec1`, no `BUZZ_PRIVATE_KEY=` value, no `ntn_`, no `Bearer ` literal.
   The 64-hex strings in the five `.toml` files and in `verify-fleet.sh` are **pubkeys**, which are
   public by construction and already in `bin/buzz_agents.env` — the assertion must permit exactly
   those and reject anything else. `buzz-notion-broker.py` reads its token from the deny-listed
   credential file at call time (`load_notion_token()`, line 46) and holds none inline; assert that
   it still reads rather than embeds.

### B — Drift, in both membership directions

4. `bin/check_deploy_drift.sh` compares a **fifth** tree: `buzz-team/` ↔ `~/.config/buzz-team/`.
   Both directions. Source-only means the box is not running what the repo says; box-only means a
   rebuild from source loses it. The existing four comparisons are unchanged.

5. The declared exclusions do **not** read as drift, and an **undeclared** file appearing in either
   tree **does**. Demonstrate both against a synthetic tree — every tree in this checker is already
   overridable for exactly this reason (`DRIFT_ETC`, `DRIFT_SRC_USER`, `DRIFT_USER`); add
   `DRIFT_SRC_BUZZ` / `DRIFT_BUZZ` in the same shape.

6. Ownership still **fails closed**: a `buzz-team/` file with no `MANIFEST.toml` entry is RED, and
   a missing `MANIFEST.toml` is a **refusal to run**, matching the existing treatment of
   `design/unit-ownership.toml` (`check_deploy_drift.sh:133-142` — *"a daily alert that is wrong
   every day is worse than no check"*).

7. Off-box behaviour is unchanged in kind: the fifth comparison joins the existing skip rather than
   inventing a second one, and `tests/ci-expected-skips.txt` is updated **only if the printed line
   changes**. CI diffs that set; a skip line that changes silently is the failure this file exists
   to prevent.

### C — Convergence is a separate act, and it is not this checker's

8. `bin/deploy_buzz_team.sh` writes `buzz-team/` → `~/.config/buzz-team/`, additive, never touching
   the declared exclusions or `backups/`.
   **Do not extend `bin/deploy`.** Its single `$DEST` is guarded by three refusals that are all
   about the agent-workforce runtime tree — `bin/agent_propose.sh` must be present, `.git` must be
   absent, the dir must exist (`bin/deploy:36-48`). A config directory satisfies none of them, and
   loosening those guards to fit a second destination weakens the guard that protects the first.
   The new script carries its own destination guard: refuse unless the target already contains the
   five rule files.

9. The converge script **does not restart any unit**, and says so on exit. buzz-acp loads
   `--config` rules at **startup**, and filter compilation is **eager** — a malformed expression
   crash-loops the unit rather than failing quietly at dispatch. So a converge is inert until a
   restart, and a bad converge is a five-agent outage. Print the restart command; let a human run
   it. This is the machine `CLAUDE.md`'s first debugging trap ("a config edit is inert until the
   process reloads it") applied to the one tree where it costs the whole fleet.

10. `--dry-run` exists and is the documented first step, matching `bin/deploy`'s contract.

### D — The DAG becomes an assertion instead of a comment

The dispatch rules are the loop guardrail. Today they are five hand-maintained files whose
agreement with `design/agents/*.toml` is stated in prose and checked by nothing in this repo.

11. For each persona, `surfaces.interactive.admits` in `design/agents/<name>.toml` equals the author
    set of `buzz-team/<name>.toml`, **both directions**. Resolve pubkey → slug through
    `bin/buzz_agents.env` plus the two declared non-agent identities (owner `82cfc202…616f`,
    praetorium `b0a6d15f…6fcd`). A pubkey resolving to neither is RED.
    Current live state, which the assertion must reproduce and not invent:
    marcus `[owner, praetorium]`; claudius/augustus/trajan `[owner, praetorium, marcus]`;
    aurelian `[owner, praetorium, marcus, claudius, trajan, augustus]`.

12. **Every rule in every file carries `require_mention = true`.** This is not style. Config mode
    merges the flag across every rule applying to a channel and a single `false` sets
    `require_mention = false` for that channel's **whole subscription, for every author**
    (`buzz-acp/src/config.rs:1499-1500`, and again at `:1408-1409`). One relaxed rule in one file
    widens a channel for everyone.

13. **No worker file admits another worker.** claudius, augustus and trajan admit only owner,
    praetorium and marcus. aurelian is the sole exception and is a **sink** — his verdicts are
    accepted by the relay and dropped at the recipients' dispatch, so the edge is one-way by
    construction. Assert the asymmetry, not just the contents: a symmetric worker→worker edge is
    the one that turns a fan-out into a cascade.

14. aurelian appears in **no** route's `notify` and in **no** slug in `bin/buzz_agents.env`.
    `tests/test_fleet_guards.sh:174` already asserts the second half; the first half is new and
    belongs with it — a route that could wake the read-only verifier is a route that can be made to
    execute by a scheduled job.

### E — S1 enters the registry

15. Each live persona gains one `[[workflows]]` entry with `surface = "interactive"`,
    `unit = "buzz-agent@<name>"`, `scope = "user"`, `status = "standing"`, and a non-empty `suite`.
    `trigger` is event-driven, not an `OnCalendar` — state the value the checker accepts and
    confirm `test_workflow_coverage.py` tolerates it rather than reading it as a missing schedule.
    `model` and `profile` come from deny-listed files; use the manifest's existing convention for
    unreadable values (`marcus.toml:55` takes `model` "from the run log, not the deny-listed env")
    and do **not** guess.

16. **`config/fleet-units.tsv` gains a `kind` column** (`timer` | `service`), and every consumer
    reads it. Without this, criterion 15 puts five `Type=simple` units with no timer into a list
    three reporting jobs walk looking for `LastTriggerUSec`, and each will render a permanently
    live agent as a unit that has never fired.
    This touches `tests/test_fleet_ownership.sh:70` (asserts **four** tab-separated columns) and
    `:74`, plus `bin/overnight_pre_snapshot.sh`, `bin/praetorium-status.sh` and
    `bin/local_tier_eval.sh`. Change the column and its assertions in the same commit —
    `fleet-units.tsv`'s own header forbids a seventh list, and a consumer that needs a subset
    **filters** this file.
    **Demonstrate the failing case**: a `service`-kind row must not be reported as a missing timer,
    and prove it by running the consumer, not by reading it.

17. Adopting `fleet-turn-check.sh` and `verify-fleet.sh` **falsifies two existing exemptions**:
    `design/agents/trajan.toml:63` reads `suite_exempt = "script lives at
    ~/.config/buzz-team/fleet-turn-check.sh, not in this repo"`, and `design/eval-spec.md:153` says
    the same. After adoption the stated reason is false. Either write the suite or restate the
    exemption with a reason that is true — **do not leave a true-looking exemption whose premise
    the same commit removed.** Whichever is chosen, say so in the brief's own record. Note the
    honest option may make the gate redder; that is the correct direction.

### F — The behavioural contract for DM, channel and forum

The three ways an S1 turn fails are all silent, all receipted `ok`, and all invisible in the journal
(`buzz-agent@*` logs lifecycle only — start, shutdown, subscribe, reconnect — and never a line per
message dispatched).

18. `design/contracts/buzz-interactive.md` states the three obligations, each with its failure mode
    and its evidence:
    - **Send.** buzz-acp never auto-publishes. A turn that computes an answer and ends publishes
      nothing, and reports `ok`. Only `buzz messages send` publishes.
    - **Kind.** The kind belongs to the **destination**, not the sender. `bin/buzz_routes.env` is
      its owner: `ops` and `signals` are streams (kind 9); `research`, `content`, `bd` and
      `approvals` are forums (kind 45001). A kind-9 post into a forum is accepted by the relay,
      receipted `ok`, and rendered to nobody. This has recurred **after** the table was deployed —
      one thread carried 45001 then kind 9 forty-eight minutes apart — which is the evidence that a
      prose rule is not a mechanism.
    - **Mention.** A mention that does not resolve is sent with **no `p` tag**; it reaches the
      channel addressed to nobody and every agent correctly ignores it. It is indistinguishable
      from a dead unit. Diagnose from the event's tags, and note the read-back trap: `buzz messages
      get` exposes `tags`, **not** `p_tags` or `reply_to` — a checker reading invented field names
      prints empty and imitates the real failure exactly.

19. The kind table keeps **one** owner and gains a gate. `check-team-kinds.py` is adopted (criterion
    1) and runs inside `bin/verify.sh`, box-gated via `box_only_with` because the file it checks
    (`TEAM.md`) is deliberately **not** adopted. Its own docstring already fixes the direction:
    `buzz_routes.env` is the owner and TEAM.md is the follower. Note it defaults to reading the
    **deployed** route table (`~/agent-workforce/bin/buzz_routes.env`), which is correct for a live
    check and wrong for a repo gate — pass the source path explicitly and say why in the call site.

### G — Gate

20. `bash bin/verify.sh` is run and its output recorded in the brief's own STATE banner, with every
    delta from brief 6's baseline accounted for by name.
    **This brief ships RED and that is not a defect.** Three independent reasons, none of which
    this brief may clear:
    - **W6** — four standing workflows name no suite and one suite has no owner. It is the standing
      PR-gate blocker; no brief in the queue closes it.
    - **Deploy drift** — the documented feature-branch condition. This brief adds `bin/` files and
      a fifth tree, so the drift count rises. Deploying an unmerged branch to the live runtime is
      not this brief's to do.
    - **Criterion 15** adds five standing workflows, and criterion 17 may convert an exemption into
      a real gap.
    **Never soften a check to change this number.** If a check goes red, the input is wrong.

---

## Files to create

- `buzz-team/` — the eighteen adopted files, byte-identical at adoption (criterion 1).
- `buzz-team/MANIFEST.toml` — adopted set, excluded set, the mechanism-vs-prose rule (criterion 2).
- `bin/deploy_buzz_team.sh` — the converge path, `--dry-run`, own destination guard, no restart
  (criteria 8-10).
- `tests/test_buzz_interactive_harness.sh` — the DAG assertions (criteria 11-14), the no-key-material
  assertion (criterion 3), and the drift-exclusion cases (criterion 5). Box-gated with
  `box_only_with` for anything reading `~/.config/buzz-team/`; the repo-side half must run
  everywhere, since `buzz-team/` is now **in** the checkout and a hosted runner can assert it.
- `design/contracts/buzz-interactive.md` — the three obligations (criterion 18).
- Possibly `tests/test_fleet_turn_check.sh` — only if criterion 17 is resolved by writing the suite
  rather than restating the exemption.

## Files to modify

- `bin/check_deploy_drift.sh` — fifth tree, both directions, `MANIFEST.toml`-driven exclusions,
  fail-closed refusal, `DRIFT_SRC_BUZZ`/`DRIFT_BUZZ` overrides (criteria 4-7).
- `tests/test_deploy_drift.sh` — the new comparison's own assertions, each demonstrated red against
  a broken input before being kept.
- `design/agents/{marcus,claudius,augustus,trajan,aurelian}.toml` — one `[[workflows]]` interactive
  entry each (criterion 15); `governed_by` repointed from `~/.config/buzz-team/<name>.toml` to
  `buzz-team/<name>.toml`, with the live path named in `notes` — the repo is now the source and the
  box path is the destination, and the field must say which; trajan's `suite_exempt` per criterion 17.
- `config/fleet-units.tsv` — the `kind` column and five new rows (criterion 16).
- `tests/test_fleet_ownership.sh` — four columns becomes five, at `:70` and `:74` and in the
  manifest↔tsv join at `:82`/`:84`.
- `bin/overnight_pre_snapshot.sh`, `bin/praetorium-status.sh`, `bin/local_tier_eval.sh` — read the
  `kind` column; a `service` row is never reported as a missing timer.
- `bin/verify.sh` — call `check-team-kinds.py` against the **source** route table (criterion 19).
- `design/fleet-suites.toml` — register the new suite. `no-orphan-suite` will **not** flag its
  absence (W12: it only reports an unclaimed suite whose subject is exec'd solely by an archived
  unit), so registration is deliberate, not gate-driven.
- `design/agent-model.md` §7 — S1 moves from "inert until Phase B" to wired; §2's S1 row gains the
  repo-side `governed_by`.
- `design/open-decisions.md` — a W-row for whatever criterion 17 leaves open, and the Carried-work
  table's S1 entry.
- `design/workflow-registry.md` — the interactive entries, so the registry and the manifests still
  agree on who owns what.
- `design/phaseb-brief-queue.toml` — this brief as entry 7, with its `must_carry` facts.
- `docs/runbook.md` — a § for the S1 tree: adopt → edit → dry-run → converge → **restart** → gate 7.
- `tests/ci-expected-skips.txt` — only if a printed skip line actually changes (criterion 7).

## Test plan

The gate is `bash bin/verify.sh`. What makes it **mean** something for this feature:

- **Every new assertion is demonstrated red against a broken input before it is kept.** Break the
  input, never the assertion. Specifically: a rule file with `require_mention = false` on one rule;
  a manifest `admits` list with one extra slug; a worker file admitting another worker; an
  undeclared file in each of the two buzz-team trees; a `service`-kind row fed to a timer consumer.
- **Both membership directions are proven separately** for the fifth tree — source-only and
  box-only are different bugs with different fixes.
- **Every suite carries the `yes | grep -q y` canary.** `grep -q` exits on match and SIGPIPEs its
  producer; under `pipefail` a *found* pattern reports 141. It disabled every
  `no artifact attached`-style assertion in this gate until 2026-08-09 while reading as an
  intermittent red. `assert()` scopes `pipefail` off; sites outside an `assert` drop the early exit
  (`grep … >/dev/null`) or the pipe.
- **Off-box, the repo-side half still runs.** `buzz-team/` is in the checkout, so the DAG
  assertions (11-13) and the key-material assertion (3) must **not** be box-gated. Only the
  comparisons against `~/.config/buzz-team/` skip. Getting this wrong hands CI a suite that skips
  whole and asserts nothing.
- **Verify convergence by running it `--dry-run`**, and confirm it lists zero changes immediately
  after adoption. A non-empty dry run at that moment means criterion 1's byte-identity failed.

## Out of scope / do not touch

- **`~/.config/buzz-agents/**` — deny-listed and outside this repo.** The per-agent `.env`
  (private key + auth tag) and `.prompt` (the persona charter). Do not read them, do not attempt to,
  do not route around the deny-list with Bash. The charter has no repo source and this brief does
  not give it one; anything needing a charter edit is a **handoff** stating the exact change.
- **`TEAM.md`, `heartbeat.prompt`, `aurelian-calibration.md`** — declared excluded (criterion 2).
  Do not adopt them, do not edit them, do not copy their content into the repo.
- **Restarting any `buzz-agent@*` unit.** Five live agents. The converge script prints the command;
  a human runs it.
- **Minting identities, relay membership, Desktop, `@`-menu behaviour.** Minting needs the owner
  key, which this box does not hold.
- **Any outward action.** No email, no social, no messaging humans. The box holds no outward
  credential and this brief adds none.
- **`/etc/systemd/system`** — root-owned. No `sudo` in any script in this repo.
- **W6.** It keeps the gate red and closing it is a brief of its own.
- **Brief 6's D5 half** — deleting the two content-research campaign units. Not before
  **2026-09-04 01:30**, and not this brief's. `Persistent=true` does not re-fire a slot that fired
  and failed; a night deleted early is lost permanently.
- **Widening `no-orphan-suite` (W12).** It would change what green means for the whole gate.
- **`bin/deploy`'s `PATHS` array and its three destination guards** (criterion 8).

## Notes / preconditions

Confirmed on the live box 2026-09-03 unless dated otherwise. Anything below that a run finds untrue
is a finding — correct it in the brief rather than working around it.

- **Upstream was read, not remembered.** `github.com/block/buzz` cloned at `40220d5`
  (2026-09-03). Three behaviours verified in source rather than from this box's lore:
  - **DMs are not a separate path.** One listener handles both: inbound author gate
    (`--respond-to owner-only` ∪ allowlist ∪ same-owner siblings) → `match_subscription` against the
    config rules (`lib.rs:3478-3493`). There is **no DM exemption from `require_mention`**, and
    `channels = "all"` matches a DM channel like any other. So criterion 12 governs DMs too.
  - **`is_dm_channel` fails closed to DM** on an unresolved channel type (`lib.rs:770-783`),
    deliberately — an agent-initiated DM is exactly a channel the agent learns about after startup.
  - **A channel with no matching rule is not subscribed at all** (`config.rs:1505-1508`).
    Config mode ignores `--channels` and uses rule-matching instead.
- **The five live units** are `buzz-agent@{marcus,claudius,augustus,trajan,aurelian}.service`,
  all `active running`, plus `buzz-notion-broker.service`. Templated from
  `~/.config/systemd/user/buzz-agent@.service`, whose source **is** in this repo at
  `systemd/user/buzz-agent@.service` since brief 2.
- **The unit reads six files from the adopted tree**: `%i.toml` (`--config`),
  `heartbeat.prompt` (excluded, prose), `buzz-team-mcp.py` (`--mcp-command`),
  `buzz-acp-launch.sh` (`ExecStart`), `claude-agent-wrapper.sh` (`CLAUDE_CODE_EXECUTABLE`), and
  through that wrapper, `agent-settings.json`. Five of the six are adopted.
- **augustus is the exception everywhere.** A drop-in swaps his harness to `codex-acp`, so
  `CLAUDE_CODE_EXECUTABLE` and `agent-settings.json` are **inert for him** — his connector absence
  is a property of his harness, asserted separately
  (`test_fleet_guards.sh::augustus-no-claude-connectors`). Do not credit the wrapper for him; that
  is §6.1's defect in miniature and it survives the removal of whatever actually held the line.
- **`bin/deploy` ships eight paths and `design/` is not among them.** `~/agent-workforce/design`
  does not exist. Anything reading a manifest at run time works in the repo and silently empties in
  the tree systemd execs — which is why `config/fleet-units.tsv` is a committed projection and not
  generated. The same reasoning applies to `buzz-team/`: it is read from `~/.config/buzz-team/` at
  run time, never from the repo.
- **`bin/check_deploy_drift.sh` cannot run from its own deployed copy.** `REPO` resolves from `$0`,
  so a copy exec'd out of the runtime tree compares that tree with itself and reports zero findings
  whatever the repo contains. That was the shipped state of `agent-drift-check.service`. The fifth
  comparison inherits the same guard — do not add a path that defeats it.
- **`LC_ALL=C` on every sort feeding `comm`.** `comm` compares bytes, `sort` collates by locale, and
  they disagree over `@` — which the new `buzz-agent@<name>` entries contain. A locale sort makes
  `comm` emit "not in sorted order" and **skip lines**, failing toward "nothing new". That is the
  one direction a drift check must never fail in.
- **`verify-fleet.sh` gate 7 already checks config freshness** against
  `ExecMainStartTimestamp` — reuse it after a converge rather than writing a second one.
  `~/.config/buzz-agents/check-loaded.sh` is its sibling for the deny-listed half and reports
  `STALE` / `BADAUTH` / prompt-behind-GUARDRAILS.
- **The machine `CLAUDE.md` has its own `## Verification` block** naming `verify-fleet.sh` +
  `check-loaded.sh`, and states explicitly that it covers machine-level fleet state and does **not**
  govern projects under `~/dev`. This brief pulls the *checker* into the repo gate. It does not
  dissolve that boundary, and the runbook § must say which gate owns what, or the next reader will
  run one and believe they ran both.
- **`design/agents/*.toml` `[[must_not]]` blocks must be arrays of tables**, never an inline array
  after a `[[workflows]]` block — TOML would scope it into that workflow. Every manifest parses
  under `tomllib` and a test asserts it still does.
- **The manifest key is `workflows`, plural.** A `tomllib` walk keyed on the singular silently
  returns zero entries and reports full coverage.
- **`bin/agent_propose.sh` is irrelevant here and must not be touched.** S1 never execs it. The
  `AGENT_OWNER` fix (W1) keys the hermes file store that the *scheduled* jobs write; Buzz agents use
  NIP-AE relay engrams (per-pubkey, injected once per **session**, not per turn) plus the shared
  Claude Code file memory at `~/.claude/projects/-home-dave/memory/`. The two memory layers do not
  meet, and this brief does not join them.
- **Commit immediately after editing.** `agent-workforce-auto-sync.timer` fires every 15 minutes and
  pushes any dirty tree to `origin/main` under a generic `Auto-sync:` message. For a long batch,
  stop the timer first and restart it after.
- **Never `--no-verify`.** It is a `must_not` rule in its own right (`design/agents/trajan.toml`).
- **This repo is public.** Nothing client-identifying enters it. Criterion 3 is the mechanical half
  of that; the mechanism-vs-prose rule is the judgement half.
