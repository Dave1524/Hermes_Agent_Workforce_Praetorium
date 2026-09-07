# Brief: agent-to-agent task scheduling on Buzz — establish it, then make it work or record that it cannot

**Date:** 2026-09-07
**Verify:** `bash bin/verify.sh` (repo root) for anything under `~/dev/agent-workforce`;
`~/.config/buzz-team/verify-fleet.sh` + `buzz-team/check-loaded.sh` for anything that touches the
five `buzz-agent@*` units. **Both gates, because the remedy spans both domains.**
**Deploy ordering:** edit → `bin/deploy` → `bash bin/verify.sh` → commit. `bin/check_deploy_drift.sh`
is inside the gate, so the gate is RED until `bin/deploy` runs. Expected, not a bug.

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

1. The relay's workflow support is **established by running a command**, not inferred. Record the
   output and the date in this brief's follow-up, and in `design/open-decisions.md` W20.
2. If the relay supports workflows: both binaries are upgraded to a build at or past the release
   carrying #6953, and the three tag literals are **present** in the new `buzz-acp` — re-run the
   same `strings` check that produced the table above, so the fix is proven by the measurement that
   found the defect.
3. A minimal `schedule` workflow (interval ≥60s, one `send_message` step naming one agent in the
   stored template) fires and **wakes that agent**, proven from the journal and the agent's CPU
   footprint (`systemctl --user show buzz-agent@<name> -p CPUUsageNSec` against an idle sibling),
   **not** by asking the agent whether it woke. Absence of logs is not absence of work here.
4. If the relay does **not** support workflows, or the upgrade is refused: that is recorded as the
   answer, W20 is closed as `DECIDED — not available`, and the §"already works" path below is
   documented as the supported mechanism. A "cannot" that is written down beats one that is
   rediscovered every few weeks.
5. Defect 1 is decided explicitly either way: agents are granted workflow authoring through the team
   instruction layer, or the base prompt's `list, trigger, runs` is recorded as intended and agents
   stop being asked to schedule. Today it is neither — it is an undocumented refusal.
6. Both gates green.

## Files to modify

- `design/open-decisions.md` — add **W20** to § Carried work (row drafted in this brief's commit).
- `design/agent-model.md` — S1's description does not mention that scheduled workflow wake is
  unavailable on this harness. One sentence, with the binary date, so the next reader does not
  re-derive it.
- `.claude/briefs/current.md` — point at this brief.

## Files to create

- Nothing yet. The upgrade is not a repo change, and no test is worth writing before criterion 1
  answers whether the mechanism exists at all. If it does, a `tests/` assertion that the installed
  `buzz-acp` carries `buzz:workflow-mention` is the right join — it is the exact check that would
  have caught this, it is cheap, and it fails closed.

## Test plan

Deliberately thin until criterion 1 lands, and that is a decision rather than an omission.

- **Nothing here is mechanisable today**, because the thing to assert lives at
  `~/.local/bin/buzz-acp` — a machine-level path with no source in any repo, the same fifth-tree
  asymmetry brief 7 dealt with for `~/.config/buzz-team/`. Note it; do not fix it here.
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
- **Restarting the five `buzz-agent@*` units.** The binary upgrade requires it and it takes the live
  chat surface down; it is a fleet operation, sequenced here and performed by Dave.
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
