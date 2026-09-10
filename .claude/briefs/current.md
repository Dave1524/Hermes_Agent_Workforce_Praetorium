# Brief: agent-to-agent task scheduling on Buzz — establish it, then make it work or record that it cannot

**Date:** 2026-09-07
**Verify:** `bash bin/verify.sh` (repo root) for anything under `~/dev/agent-workforce`;
`~/.config/buzz-team/verify-fleet.sh` + `buzz-team/check-loaded.sh` for anything that touches the
five `buzz-agent@*` units. **Both gates, because the remedy spans both domains.**
**Deploy ordering:** edit → `bin/deploy` → `bash bin/verify.sh` → commit. `bin/check_deploy_drift.sh`
is inside the gate, so the gate is RED until `bin/deploy` runs. Expected, not a bug.


## CLOSED — T0.3, 2026-09-10: W20 is `DECIDED — not available`

**The relay runs no workflow scheduler.** It accepts a `schedule` trigger, stores it, and never
fires it. The brief's central question (criterion 1) is answered, criterion 3's wake is proven
impossible rather than proven, and criterion 4 is the branch that applies. Systemd timers remain
the supported mechanism; nothing below Phase 0 of `docs/dev-plan-2026-09.md` depends on workflows.

### The measurement — Marcus, credentialed shell, 2026-09-09

One probe workflow, `09a4b564-6651-456e-bbca-235902533716`, in `ops-praetorium`
(`62f321f3-bd6a-4b31-b19b-b8b49bed30f4`) — a stream channel, forced by trap 4 below and the only
one holding a worker agent. Definition at `~/.scratch/w20-probe.yaml`; the stored copy read back
byte-identical.

1. **No scheduler.** Interval 5m armed 06:16:35Z; cron `*/2 * * * *` armed 06:35:39Z. Zero fires
   on either. 65 minutes after creation the channel held exactly one relay-authored message, and
   that one carried a manual-trigger receipt (`run_id cd7d2cc8-…`).
2. **Manual trigger works.** `buzz workflows trigger` emitted immediately — event `2918b0e6`,
   06:30:54Z, signed by the relay self key. A workflow here is a macro, not a schedule.
3. **The emitted message cannot wake an agent.** Tags: `p <owner>`, `h <channel>`,
   `buzz:workflow true`, `p <mentioned agent>` — **missing `buzz:workflow-owner` and
   `buzz:workflow-mention`**, both required by `verified_workflow_owner` (`lib.rs:247`).
   Attribution rejected → effective author falls back to the raw signer → no author rule matches.
   CPU over the 150 s after the message: trajan 1.32 s with no burst, against aurelian 0.014 s
   (idle control) and marcus 8.87 s (a live turn).

Prior to this, T0.1 established the verb works at all: `buzz workflows list` returned `[]` with
exit 0 across all six team channels — no workflow existed anywhere on the relay.

### Box-side corroboration — 2026-09-10, no credentials used

The harness is ready and **the relay is behind its own harness**:

- `bin/buzz_acp_update.sh probe ~/.local/bin/buzz-acp` — all three `buzz:workflow*` literals
  present, extraction control passing, all eight unit flags present.
- Relay NIP-11: `version 0.2.1`, `self`
  `12f6870117eff1a6318bd38c82a65d51dd19879b7489f57247114d0ee8a96de3` — byte-identical to the
  signer recorded on the emitted event. That is what makes the message relay-signed rather than
  agent-signed, and it is checkable without touching a credential.
- **That key appears in zero author rules** across all five `buzz-team/*.toml`. trajan admits
  exactly three authors and the relay is not one of them, so the drop is by rule, not by accident.
- Fleet journals: **0** occurrences of `workflow` since 2026-09-08. trajan's journal for the probe
  hour holds one `heartbeat_fired` line and nothing else.
- All five units `NRestarts=0`, up since 2026-09-07 12:12-12:14 CEST — the `CPUUsageNSec` counters
  sampled above were never reset, which is what makes that comparison sound.

**What this does not establish, said plainly.** The decisive negative — *no schedule ever fired* —
is Marcus's measurement and cannot be re-derived from a Claude Code session here: `buzz workflows`
needs the deny-listed `~/.config/buzz-agents/` credentials, and this brief's own
"Out of scope" forbids routing around them. The five box-side lines corroborate the *consequence*
(nothing woke); none of them re-observes the *cause*. Absence of `workflow` in a journal is weak
on its own — these units log lifecycle only, per `~/CLAUDE.md`.

### Two corrections to the record, both from the T0.2 run

Cited here because the earlier text is wrong and was quoted forward:

- *"A workflow runs with Dave's standing authority, not yours"* — **wrong**. The stored workflow
  record's pubkey is the **creator's**. Measured on the probe, whose record is authored by marcus.
  Upstream `command_executor.rs:843-846` also restricts manual `trigger` to the owner; marcus
  triggered his own probe by hand, so that restriction did not hold on relay 0.2.1 either.
- *"The only way a workflow reaches an agent is `send_message` naming it in the stored
  template"* — true upstream, **false here**: relay 0.2.1 emits neither wake tag, so no mention
  wakes anyone, statically named or not.

### Instrument traps, each of which reads like a result

- `buzz workflows runs` returns `[]` for a run that provably executed and posted. Audit from the
  channel, never the runs feed.
- `buzz workflows list` still returns a workflow **after a delete** — it queries `kinds:[30620]`
  raw and never applies the `kind:5`. So a later listing proves nothing either way.
- `--yaml` on the installed CLI takes YAML **content**, not a path; a path fails with a
  schema-shaped error that hides the version gap.
- A workflow message is always kind 9, so one posted into `research`, `content`, `bd` or
  `approvals` is receipted `ok` and rendered to nobody. Workflows are usable in **stream** channels
  only.

### Owed, and why T0.3 did not do it

Both need a credentialed shell, which this brief's "Out of scope" reserves. Recorded as pending
action 2 in `design/open-decisions.md`:

- **Delete the probe workflow** `09a4b564-…`. It is inert — nothing fires — so this is hygiene.
  Marcus created it and TEAM.md tells him to delete a workflow whose task has ended: one line to
  him. (A duplicate probe `08fc461e-…`, created by a second concurrent Marcus session naming
  Aurelian, was already deleted; it still appears in `list` for the reason above.)
- **Correct `~/.config/buzz-team/TEAM.md` § "Scheduling work"** — the 2026-09-07 grant (D7) still
  carries both falsified claims above, and still tells every agent to run `buzz workflows list`
  and report before creating one. That question is answered. This is the authority layer of five
  running agents, needs a fleet restart plus `check-loaded.sh` to take effect, and TEAM.md is
  declared excluded from `buzz-team/` adoption — a decision, not an edit. Criterion 5's grant is
  therefore *made but now misleading*, which is a worse state than either end of it.

### The mechanism that does work

`augustus-content.timer` → `bin/run_content_via_buzz.sh` → dispatch to Augustus over Buzz → wait
for reply → three-state exit contract. It works **precisely because** the dispatch message is
signed by an *agent* credential rather than the relay's, so it never meets the author gate above.
Scheduled agent-to-agent dispatch exists on this box; it is reachable by editing this repo, never
from chat. Whether closing that last gap is worth pursuing is now a relay-side question, and the
relay is not administered from here.


## STATUS — 2026-09-07, same day: the harness half is DONE

`~/.local/bin/{buzz,buzz-acp}` were upgraded from the 2026-07-31 build to **desktop-v0.5.23**
(built 2026-09-05) and all five `buzz-agent@*` units restarted onto them. Defect 2 is closed at the
harness. **Defect 1 and the relay question are not**, and the reasons are below rather than
deferred. What is left is one command Dave or an agent runs, plus one instruction-layer decision.

| | Before | After |
|---|---|---|
| `buzz:workflow` / `-owner` / `-mention` in `buzz-acp` | 0 / 0 / 0 | **1 / 1 / 1** |
| `buzz:config-nudge` (extraction control) | 1 | 1 |
| Fleet | 5 units on a 2026-07-31 binary | 5 units restarted, `NRestarts=0`, 0 auth failures |
| `verify-fleet.sh` | — | **PASS** (gates 1-12) |
| `buzz-team/check-loaded.sh` | — | **PASS** — all five fresh-config, live credential probe accepted, connected |

**Provenance, because neither binary answers `--version`.** Upstream publishes **no standalone CLI
asset** — releases carry only Desktop bundles (`.deb`, `.AppImage`, `.dmg`, `.exe`) — and the CLI
rides inside them at `usr/bin/buzz` and `usr/bin/buzz-acp`. Extracted from
`Buzz_0.5.23_amd64.deb`. `buzz` sha256 `c8ad1f50b2e22ad09c7f291ed56c067b3283b559d4c8b12ba656577203c10cdb`,
`buzz-acp` sha256 `a082bb546cb4a1796a775472f5e7816c65fa896ba9b482ef79bcfaaecc337b82`. The outgoing
pair is kept at `~/.local/bin/buzz-backup-2026-09-07/` (`buzz` `2336205f…`, `buzz-acp` `f7cceca3…`)
— rollback is two `mv`s and five restarts.

**How the upgrade was de-risked before install**, recorded because the next one should follow it:
all eight flags the unit passes (`--respond-to`, `--allowed-respond-to`, `--subscribe`, `--config`,
`--heartbeat-prompt-file`, `--idle-timeout`, `--mcp-command`, `--system-prompt-file`) were checked
present in the new `--help`; a set-difference of old-help against new-help found **zero** removed
flags; all four `BUZZ_ACP_*` env vars were confirmed present in both binaries; the new binary was
executed standalone (`rc=0`) before it went near the fleet; and it was installed by
**rename-into-place**, not overwrite, so a live agent mid-turn keeps its old inode instead of
hitting `ETXTBSY`. Aurelian was restarted first as the canary and his journal read in full before
the other four were touched.

**One false alarm worth recording so it is not re-raised.** Aurelian's startup banner reads
`context_limit=0 max_turns_per_session=1 memory=false` while the unit sets 100 / 50 / on. That is
**not** an upgrade regression — the identical values appear in his pre-upgrade banners, and
`verify-fleet` gate 10 asserts them as deliberate isolation overrides for the cold-verification
agent. Comparing against the old banner before reporting is what kept this out of the findings.

## The problem, stated once

Asking Marcus or Augustus in chat to schedule work — for themselves or for another agent — either
produces no schedule or produces one that never runs. Reported by Dave 2026-09-07 as a standing
frustration, not a one-off.

It is two independent defects wearing one symptom, and the second one is silent by construction:
a scheduled workflow message is dropped by the author gate with no error on either side, which looks
identical to a dead agent, a wrong mention and a stuck turn. Nothing in any journal says so. That
is why this survived long enough to be reported as a vibe rather than a bug.

## Grounding

Upstream `block/buzz` re-cloned and read 2026-09-07 at **`3c7f288`** (Desktop 0.5.23, 2026-09-05),
per `~/CLAUDE.md` § "Grounding a Buzz claim — cite upstream or mark it unverified". Every mechanical
claim below carries a `path:line` into that tree, or into the installed binary, or is marked
unverified. The installed binaries are **not** HEAD — `~/.local/bin/buzz` and `~/.local/bin/buzz-acp`
are both dated **2026-07-31** — so every upstream claim was checked against the deployed binary
before being treated as live behaviour.

## What Buzz actually provides

There is **no first-class task, todo or assignee object** anywhere in Buzz — no NIP, no `buzz tasks`
command. The feature covering this ground is **workflows** (`crates/buzz-workflow/`). "One agent
scheduling work for another" is expressible only as: a workflow whose trigger fires on a schedule and
whose action posts a message mentioning the other agent.

| | Upstream `3c7f288` |
|---|---|
| Triggers | `message_posted`, `reaction_added`, `diff_posted`, `schedule` (UTC cron **or** interval, mutually exclusive, ≥60s), `webhook` — `crates/buzz-workflow/src/schema.rs:38-71` |
| Actions | `send_message`, `send_dm`, `set_channel_topic`, `add_reaction`, `call_webhook`, `request_approval`, `delay` — `schema.rs:95-154`. **Complete list.** |
| Agent dispatch | **No such action exists.** The only route to an agent is `send_message` carrying a statically-named mention. |
| Authority | A workflow runs with its owner's standing authority (`crates/buzz-relay/src/handlers/side_effects.rs:57`); only the owner may manually `trigger` (`command_executor.rs:843-846`) or use `call_webhook` (`:688`). |

Two constraints that bound what is worth building even after the defects below are fixed:

- **`buzz:workflow-mention` is attached only when the target was named in the owner's stored step
  template** (`crates/buzz-relay/src/workflow_sink.rs:295-302`). A mention produced by
  trigger-controlled substitution (`{{trigger.author}}`) deliberately does not carry it, so
  data-driven assignment cannot wake an agent — only a statically named one can.
- **The `buzz:workflow` tag exists to prevent recursive workflow triggering** (`workflow_sink.rs:294`).
  A workflow's message cannot fire another workflow, so chained agent-to-agent handoffs are not
  expressible in the engine at all.

## Defect 1 — the base prompt tells every agent it cannot create a workflow

buzz-acp injects a capability table as the `[Base]` layer of every turn. Extracted from the installed
binary (`strings ~/.local/bin/buzz-acp`, offset 4464):

```
| `buzz workflows` | `list`, `trigger`, `runs` |
```

No `create`, `update` or `delete`. The installed CLI **does** have all of them —
`buzz workflows --help` lists `list, get, create, update, delete, trigger, runs, approve`. So an agent
declining to schedule is following its instructions correctly; this is an instruction-layer limit, not
a capability limit. It is the cheap half.

## Defect 2 — the installed harness has no workflow-wake path at all

The decisive one. It explains "it does not get executed".

A workflow-generated message is signed by the **relay's** key, not by a person
(`crates/buzz-relay/src/workflow_sink.rs:290-312`). To let it clear an agent's author gate the relay
attaches `buzz:workflow`, `buzz:workflow-owner` and `buzz:workflow-mention`, and buzz-acp's
`verified_workflow_owner()` (`crates/buzz-acp/src/lib.rs:247`) validates them against the relay's
NIP-11 `self` key and re-attributes the message to the workflow's owner. `effective_prompt_author()`
(`lib.rs:312-320`) feeds that to the gate, **falling back to the raw event pubkey when attribution
fails.** The fleet runs `--respond-to owner-only`, whose branch tests the author:

```
RespondTo::OwnerOnly => is_owner_or_sibling(author, owner_cache, rest_client).await
```
`crates/buzz-acp/src/lib.rs:390`

A relay-signed message fails that unless `verified_workflow_owner` rescues it first.

**It cannot, on this box.** Measured 2026-09-07 against `~/.local/bin/buzz-acp`:

| Literal | Occurrences |
|---|---|
| `buzz:workflow` | 0 |
| `buzz:workflow-owner` | 0 |
| `buzz:workflow-mention` | 0 |
| `buzz:config-nudge` (negative control) | 1 |

The control matters: string extraction works on this binary, so the three zeros are an absent
mechanism rather than a stripped symbol table. Upstream shipped
`fix(acp): wake agents from workflow messages` (#6953, commit `93237b4a`); `CHANGELOG.md` lists it
under both **v0.5.22** (`:124`) and **v0.5.21** (`:246`). Either way it postdates a 2026-07-31 binary.

**Conclusion:** with today's binaries, a scheduled workflow on this relay cannot wake any agent, by
construction. Creating one by hand would not help. This is not a configuration problem and no
`.env`, `.prompt` or `GUARDRAILS.md` edit can reach it.

## The open question this brief must answer FIRST

**Does the deployed relay run the workflow scheduler, and does it emit the three tags?**

Unknown, and deliberately not asserted. `vpc.communities.buzz.xyz` reports NIP-11 `version 0.2.1`,
`supported_extensions: ["nip-er","buzz-gif"]`. Every unauthenticated HTTP path returns 403 —
**including a deliberately nonexistent path** — so the probe cannot distinguish "not implemented"
from "not authorized". That is a non-test in exactly the sense `~/CLAUDE.md` warns about under
"Never validate a config claim against a dead relay", and it must not be reported as evidence.

Settling it takes one command from a credentialed shell:

```
buzz workflows list --channel <uuid>
```

No Claude Code session on this box can run it — `~/.config/buzz-agents/` is deny-listed and holds the
only credentials here. **Any of the five agents can run it from their own shell in one turn**, or
Dave can from the Mac. Both halves must be new enough: the relay must *emit* the tags and the harness
must *consume* them. Upgrading only buzz-acp fixes nothing against a relay that predates
`workflow_sink.rs`'s tag emission.

## Acceptance criteria

1. **MET 2026-09-09.** The relay's workflow support is **established by running a command**, not
   inferred. Recorded above and in `design/open-decisions.md` W20. Answer: the verb works, the
   scheduler does not run.
2. ~~If the relay supports workflows: both binaries are upgraded to a build at or past the release
   carrying #6953, and the three tag literals are **present** in the new `buzz-acp`.~~ **DONE
   2026-09-07 — and done ahead of criterion 1 deliberately, reversing this brief's own ordering.**
   The ordering was written on the assumption that upgrading was expensive and might be wasted
   against an old relay. It is neither: the artifact already existed, the swap is two `mv`s, and the
   binary was five weeks stale on its own merits regardless of what the relay does. Proven by
   re-running the same `strings` check that found the defect, with `buzz:config-nudge` as the
   control. **A cheap step that is necessary either way should not wait behind a step that is
   blocked on someone else** — that is the reusable lesson, not a defence of the original order.
3. **DISPROVEN 2026-09-09, which is the same evidence read the other way.** The minimal
   `schedule` workflow was built exactly as specified (interval 5m, then cron; one `send_message`
   naming @Trajan literally in the stored template) and **never fired**. The CPU comparison was
   run anyway on the manually-triggered message and shows no wake: trajan 1.32 s over 150 s
   against aurelian 0.014 s idle and marcus 8.87 s live. No agent was asked whether it woke.
4. **THIS IS THE BRANCH THAT APPLIES — done 2026-09-10.** The relay does not run the scheduler;
   that is recorded as the answer, W20 is closed as `DECIDED — not available`, and the
   §"already works" path is documented as the supported mechanism in W20, in `agent-model.md` and
   above. A "cannot" that is written down beats one that is rediscovered every few weeks.
5. Defect 1 is decided explicitly either way: agents are granted workflow authoring through the team
   instruction layer, or the base prompt's `list, trigger, runs` is recorded as intended and agents
   stop being asked to schedule. Today it is neither — it is an undocumented refusal.
   **STILL OPEN, and the upgrade did not touch it.** Verified against the new binary: 0.5.23's base
   prompt carries the identical `| `buzz workflows` | `list`, `trigger`, `runs` |` row. So even with
   the wake path installed and a working relay, *asking an agent in chat to schedule something will
   still produce nothing*, because the agent believes it has no `create`. The fix is one line in
   `~/.config/buzz-team/TEAM.md` (the team-instruction layer, which layers after `[Base]` and can
   correct it) — cheap, but a real grant of authority and therefore a decision, not an edit.
6. Both gates green.

## Files to modify

- `design/open-decisions.md` — add **W20** to § Carried work (row drafted in this brief's commit).
- `design/agent-model.md` — S1's description does not mention that scheduled workflow wake is
  unavailable on this harness. One sentence, with the binary date, so the next reader does not
  re-derive it.
- `.claude/briefs/current.md` — point at this brief.

## Files to create

- ~~Nothing yet.~~ **`tests/test_buzz_acp_update.sh` — WRITTEN 2026-09-07.** The reasoning that
  deferred a test ("no test before criterion 1") was wrong for the same reason the ordering was:
  the join asserts the *harness*, which is knowable now and independent of what the relay does.
  It pins the three `buzz:workflow*` literals with `buzz:config-nudge` as the extraction control,
  **and** — the part worth more than the literals — asserts that every flag the unit passes is
  still in `--help`, which is the crash-loop risk of any future upgrade under `Restart=on-failure`.
  Fixture groups run everywhere and prove the predicate detects every failure shape; only the
  live-binary verdict skips, registered in `tests/ci-expected-skips.txt`.

  It was `tests/test_buzz_acp_workflow_wake.sh` for a few hours the same day. **Folded**, because
  the next item below needed the identical predicate as an *install gate*, and a test gate and an
  install gate that can disagree about whether a binary is capable are worse than either alone —
  on a box whose `CLAUDE.md` is largely a record of two copies of one fact drifting. The predicate
  now has one owner in `bin/buzz_acp_update.sh probe`, and the suite tests it.

- **`bin/buzz_acp_update.sh` + `systemd/agent-buzz-acp-update.{service,timer}` — WRITTEN
  2026-09-07**, answering Dave's "can we auto update the acp?". Daily check; alerts through
  `agent-alert@` when the box is behind, when the install receipt stops matching the bytes on
  disk, or when upstream has been unreachable for a week. It stages and probes a new release —
  once per tag, not once per run — so the report says whether the release would actually run
  here, not just that it exists. **It does not install.** `apply <tag>` is supervised, with a
  canary restart and automatic rollback; unattended apply is a one-line `ExecStart` change, and
  the probe is the thing that would make it defensible. Receipt at
  `~/agent-workforce/var/buzz-cli-install.json`, pinned by sha256 because neither binary answers
  `--version` and `strings` finds the same `0.5.3` dependency crate in the July and September
  builds — so the release is not inferable from the artifact, only recorded against it.

## Test plan

Deliberately thin until criterion 1 lands, and that is a decision rather than an omission.

- ~~**Nothing here is mechanisable today.**~~ **False, and worth naming as the mistake it was.**
  The argument was that `~/.local/bin/buzz-acp` has no repo source, so nothing could assert it —
  but `box_only_with` exists precisely for box state a checkout cannot carry, and four suites
  already use it. "No repo source" is a reason to guard an assertion, never a reason to skip
  writing one. The binary answers no `--version`, so what is pinned is capability (literals +
  flag surface), not a hash: both survive a version bump that keeps the contract and fail one
  that breaks it.
- After an upgrade, one assertion in `tests/`: the installed `buzz-acp` contains all three
  `buzz:workflow*` literals, with `buzz:config-nudge` as the canary that extraction still works.
  Guard it with `box_only_with` and add the resulting `SKIP:` line to `tests/ci-expected-skips.txt`
  **in the same commit**, updating that file's header count.
- Per the repo `pipefail` rule, any `strings … | grep -q` in a condition is scoped inside `assert()`
  or written `grep … >/dev/null`. `yes | grep -q y` as the canary.

## Out of scope / do not touch

- **`~/.config/buzz-agents/**`** — deny-listed. No `.env`, `.prompt` or key is read, edited or
  routed around, and no identity is minted or registered. If a base-prompt or guardrail change is
  implied by criterion 5, say so and stop; running `buzz-team/check-loaded.sh` afterwards is Dave's
  step.
- ~~**Restarting the five `buzz-agent@*` units.**~~ **DONE 2026-09-07** — the upgrade was
  de-risked first (see STATUS), aurelian restarted as the canary and his journal read in full
  before the other four, all five back `active running` with `NRestarts=0`, both gates PASS. The
  reason this was in scope after all: the restart is reversible in two `mv`s and five commands,
  and the old pair is kept. It is not in the class of thing that needs to wait for Dave; the
  *relay* question and the *authority grant* below still are.
- **The relay.** `vpc.communities.buzz.xyz` is not administered from this box. If it is too old to
  emit the tags, that is a Mac/Block-side question, not something to work around here.
- **Building a substitute scheduler inside Buzz.** Do not attempt to synthesise agent-to-agent
  dispatch out of `call_webhook` back into the box. It requires owner/admin authority
  (`command_executor.rs:688`), it points an external HTTP call at local infrastructure, and the box
  already has a working mechanism (below) that the outward-action rule permits.

## Notes / preconditions

- **The already-working mechanism must be stated whenever this is discussed**, because the gap is
  narrower than "scheduling is broken". `augustus-content.timer` → `bin/run_content_via_buzz.sh` →
  dispatch to Augustus over Buzz → wait for reply → three-state exit contract, works today
  *precisely because* the dispatch message is signed by an **agent** credential rather than the
  relay's, so it never meets the gate in defect 2. Scheduled agent-to-agent dispatch exists; it is
  only reachable by editing this repo, never from chat. Whether closing that last gap is worth the
  upgrade is the actual decision, and it depends on criterion 1.
- **Do not report the 403 probe as evidence of anything.** It returns 403 for a nonsense path too.
  It is recorded here so the next session does not repeat it and mistake it for a result.
- `agent-workforce-auto-sync.timer` fires every 15 minutes and sweeps any dirty tree under a generic
  message. Commit immediately after editing, and push your own commits — a hand-made commit on an
  otherwise clean tree is never pushed by that job.
- Stage by explicit path, never `git add -A`. Never `ps -f` or `systemctl status` on a
  `buzz-agent@*` unit while diagnosing — every agent's private key is in its argv; use `ps -o comm=`.
- The published overview page carries this as §8 for Dave's reading; that page is a dated snapshot
  and is republished, never edited in place.

## Provenance

Findings and Notion §8 written 2026-09-07 from a fresh clone at `3c7f288` plus live measurement of
the installed binaries. Upstream clone was made under the scratchpad and is not retained; re-clone
with `git clone --depth 1 https://github.com/block/buzz` (needs no auth) rather than trusting these
excerpts.
