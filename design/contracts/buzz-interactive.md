# Contract: buzz-interactive

The S1 surface — every DM, channel message and forum thread the five `buzz-agent@*` units
handle. Written 2026-09-03 (brief 7).

**This one breaks rule 1 of `design/contract-schema.md` deliberately, and says so.** The
rule is one contract per unit, named for the unit. There are five units here and they run
byte-identical code (`buzz-team/buzz-acp-launch.sh`, one templated
`~/.config/systemd/user/buzz-agent@.service`) against five charters this repo cannot read.
Five files would be five copies of one set of obligations, and the failure this contract
exists to prevent is *drift between copies of one fact*. So: one contract, five owners, and
each of the five `[[workflows]]` entries points here. If a per-agent promise ever differs —
aurelian's calibration pin is the candidate — that agent gets its own file and this one
names the split.

Everything below was read on 2026-09-03 from `bin/buzz_routes.env`,
`buzz-team/{marcus,claudius,augustus,trajan,aurelian}.toml`, `buzz-team/check-team-kinds.py`
and `~/.config/systemd/user/buzz-agent@.service`. Upstream mechanics cite
`github.com/block/buzz`; anything not cited and not dated is lore.

## Identity

| | |
|---|---|
| Units | `buzz-agent@{marcus,claudius,augustus,trajan,aurelian}.service` (`--user` scope) |
| Owners | each unit's own persona manifest, `design/agents/<name>.toml` |
| Surface | S1 — Buzz interactive |
| Executor | `~/.local/bin/buzz-acp` → `/usr/local/bin/claude-agent-acp`; **augustus alone** runs `codex-acp` inside a bwrap mount namespace |
| Kind | `service` — `Type=simple`, always on, **no timer**. `config/fleet-units.tsv` column 5 |
| Contract version | 1 (2026-09-03) |
| Alerted | **no.** There is no `OnFailure=` on `buzz-agent@.service`. `fleet-turn-check` is the compensating control and it is hourly, not immediate |

## Trigger

Event-driven. There is no `OnCalendar` and asking for `buzz-agent@marcus.timer` returns
nothing — `systemctl list-timers` drops an unmatched name silently, rc=0, empty stderr
(measured 2026-09-03), which is why the `kind` column exists.

A turn starts when a relay event reaches a subscribed channel **and** carries a `p` tag for
that agent's pubkey. Both halves are required and each fails silently on its own.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `~/.config/buzz-team/<name>.toml` (dispatch rules) | read **at process start only** | **silent staleness.** An edited rule file is not loaded until restart, and nothing reports the gap. Prove the running process read it: file mtime vs `systemctl --user show buzz-agent@<n> -p ExecMainStartTimestamp` |
| `bin/buzz_routes.env` → `~/agent-workforce/bin/buzz_routes.env` | source and deployed must agree | `bin/check_deploy_drift.sh` (tree 1). A source-only edit is invisible to `deliver.sh` until `bin/deploy` runs |
| `~/.config/buzz-team/TEAM.md` (the kind table agents read by hand) | must agree with `buzz_routes.env` | `buzz-team/check-team-kinds.py`, wired into `bin/verify.sh` 2026-09-03. Declared **excluded** from `buzz-team/` adoption — it names live channel UUIDs and agents edit it |
| `~/.config/buzz-agents/<name>.prompt` (charter) | deny-listed; unreadable from here | not assertable. `profile_in_repo = false` in the manifest is how that is declared rather than assumed |
| the `core` engram (NIP-AE), fetched from the relay | once per **session**, not per turn | on a transport error `engram_fetch` emits **nothing at all** (`crates/buzz-acp/src/engram_fetch.rs:9-12`) — deliberately, so an outage is never mistaken for "no core" and cannot bait an overwrite. Empty renders an onboarding nudge; errored renders silence. Check the journal before concluding the engram is empty |
| relay `wss://vpc.communities.buzz.xyz` | must be reachable at connect | buzz-acp loads `--config` rules **after** the relay connects (`crates/buzz-acp/src/lib.rs:1751`), so against a dead relay it prints its full startup banner and `agent_pool_ready` and looks healthy no matter how broken the config is. Never validate a config claim against an unreachable relay |

## Outputs

**There is no automatic output.** That is the first obligation and the whole reason this
file exists; see below.

When a turn does publish, it publishes one Nostr event to one channel, at the kind that
channel's row in `bin/buzz_routes.env` declares:

| Route key | Channel type | Kind |
|---|---|---|
| `ops` | stream | 9 |
| `signals` | stream | 9 |
| `research` | forum | 45001 |
| `content` | forum | 45001 |
| `bd` | forum | 45001 |
| `approvals` | forum | 45001 |

`45003` (forum comment) is not a legal value here: buzz-cli requires `--reply-to` for it and
no producer on this box replies to an existing thread.

## The three obligations

### 1. Send — buzz-acp never auto-publishes

A turn that computes an answer and ends publishes **nothing**, and the turn still reports
`ok`. The harness returns the model's text to the ACP session; it does not post it. Only an
explicit `buzz messages send` reaches the relay.

*Failure mode.* The agent believes it answered. The requester sees silence. Every signal on
the box is green, because from the runtime's point of view the turn succeeded — which it
did. This is indistinguishable at a glance from a dead unit, from an unresolved mention, and
from a kind mismatch; the three are separated below by *where* the event stops.

*Evidence.* Memory `buzz-acp-no-auto-publish`. The compensating control is
`fleet-turn-check`, hourly, which spends a real model turn and asserts a reply comes back —
the only check on this box that proves a turn can complete. Every other fleet signal stayed
green through a four-day outage.

### 2. Kind — the kind belongs to the destination, not the sender

Two producers writing the same channel must publish the same kind or half the traffic is
invisible to the reader. Desktop's forum view queries `kinds:[45001]` exclusively.

*Failure mode.* A kind-9 post into a forum channel is **accepted by the relay, receipted
`ok`, and rendered to nobody.** The relay does not gate content kind by channel type —
`channel_type` is read only on the channel-create path (`buzz-relay ingest.rs:372-374` vs
`:2566-2640`, upstream `02f640bc`) — so there is no error anywhere in the stack. The reverse
(45001 into a stream) is accepted too; only client rendering differs.

*Evidence, and why a prose rule was not enough.* This recurred **after** the route table was
deployed: on 2026-08-25 one thread carried 45001 and then kind 9 forty-eight minutes apart,
by the same agent. It cost twelve research runs, because a question an agent asks the owner
has no delivery receipt and no timeout. The table being correct changed nothing;
`check-team-kinds.py` in the gate is the mechanism that a rule in a file was not.

*Read-back trap.* Verifying a send has its own version of this failure.
`buzz messages get` exposes `tags` — there is **no** `p_tags` field and **no** `reply_to`
field. A checker reading those invented names prints empty and imitates the real failure
exactly. And `buzz messages thread` returns only `e`-tagged replies, so a flat answer to a
thread reads as unanswered.

### 3. Mention — an unresolved name is sent with no `p` tag

Every rule file on this box sets `require_mention = true`, and
`resolve_channel_filters` **merges** that flag across every rule applying to a channel, so a
single `false` widens the whole subscription rather than one rule.

*Failure mode.* A mention that does not resolve to a pubkey is sent with **no `p` tag at
all**. The message reaches the channel addressed to nobody, is receipted `delivered`, and
every agent correctly ignores it. It is indistinguishable from a dead unit.

*Diagnosis, in order.* The event's tags first (`buzz messages get --channel <id>`; empty
means the mention never bound), then channel membership
(`buzz channels members --channel <id>`), then the unit. Membership and relay membership are
separate gates: "not a relay member" at connect is always the auth tag, never the member
list. Addressing by pubkey bypasses the menu entirely and always binds.

*Scheduled corollary.* `bin/deliver.sh` resolves a notify slug through
`bin/buzz_agents.env`. aurelian is absent from that table **by design** — that absence is
what makes him unreachable by any timer, and `design/agents/aurelian.toml` records it as a
`must_not` with `enforced = true`, not as a TODO.

## Decline conditions

There is no `DECLINE:` sentinel on this surface; that convention belongs to
`agent_propose.sh` runs. The legitimate no-output states are:

1. **The event carried no `p` tag for this agent.** Correct: not addressed to it.
2. **The author is not admitted by this agent's rules.** The loop-guardrail DAG. marcus
   admits `owner` and `praetorium` only; the three workers admit those plus marcus; aurelian
   admits all five and **no worker admits aurelian**. That asymmetry is the calibration pin
   and `tests/test_buzz_interactive_harness.sh` asserts both halves.
3. **aurelian returns `INCONCLUSIVE`.** He executes nothing by construction; a refusal to
   verify what he cannot check is correct behaviour, not a fault.

A silent no-reply that is *not* one of these three is obligation 1 failing.

## Side effects

- Publishes a Nostr event under the **agent's own** key when it sends. The engram is
  likewise authored by the agent's key — `buzz mem set` from Dave's shell publishes under
  the *owner* pubkey and is never injected.
- May write the `core` engram. Use `buzz mem hash core` → `buzz mem patch core --base-hash`;
  a bare `set` is a blind overwrite and destroys everything accumulated since.
- Reads the vault through `mcp__qmd-mcp__*` (note the namespace — **not** `mcp__qmd__*`).
- Notion writes go through the broker socket, never a token the agent holds.
- Writes `~/.claude/projects/-home-dave/memory/`, which is shared by all five agents *and*
  Dave's own `~` sessions. Per-agent state belongs in the engram, which is genuinely
  per-pubkey.
- No outward action of any kind. The box holds no outward credential, and
  `~/.config/buzz-team/agent-settings.json` denies the claude.ai connectors for every
  `claude-agent-acp` session via `CLAUDE_CODE_EXECUTABLE`.

## Acceptance checks

Each is decidable by a command. 1–6 run in the repo; 7–10 need the box.

1. **Every rule file requires a mention.** `require_mention = true` in every `[[rules]]`
   table of all five `buzz-team/*.toml` — `tests/test_buzz_interactive_harness.sh`. One
   `false` widens the whole channel because the flag is merged, not per-rule.
2. **`admits` equals the rule files' author sets, both directions**, with pubkey→slug
   resolution through `bin/buzz_agents.env`. Same suite. An unknown pubkey is RED, not
   ignored.
3. **No worker admits another worker, and aurelian's edge is one-way.** Assert the
   *asymmetry* explicitly: he admits all five, none admits him. Same suite.
4. **aurelian appears in no route `notify` and in no slug table.** Same suite; the
   `must_not` in his manifest names it.
5. **The kind table has one owner and the follower agrees.**
   `buzz-team/check-team-kinds.py bin/buzz_routes.env ~/.config/buzz-team/TEAM.md`, wired
   into `bin/verify.sh` against the **source** route table.
6. **No key material in `buzz-team/`.** No `nsec1`, no `BUZZ_PRIVATE_KEY=<value>`, no
   `ntn_`, no credential-shaped bearer literal; every 64-hex string is one of the six
   declared pubkeys. Same suite.
7. **A turn completes.** `fleet-turn-check` hourly, and it must name a QUIET unit out loud —
   absence of attempts is not evidence of health. `tests/test_fleet_turn_check.sh` asserts
   the five properties that make its output mean something.
8. **The running process read the config it is being judged on.** File mtime vs
   `ExecMainStartTimestamp`. `~/.config/buzz-agents/check-loaded.sh` reports `STALE`.
9. **The credential halves match.** `check-loaded.sh` reports `BADAUTH` when a private key
   and auth tag come from different identities — the relay accepts the connection and then
   loops on `restricted: not a relay member`.
10. **Exactly one process answers per pubkey.** buzz-acp runs a default pool of **2**
    context-isolated sessions per pubkey, so an agent duplicates itself on the box: count
    `claude-agent-acp` children, not `buzz-acp` processes. A Desktop double-host adds a
    third head that `check-loaded.sh` reports as all-OK, because the box half genuinely is.

## Known failure modes

- **The silent success (obligation 1).** Turn computes, turn ends, nothing published, `ok`
  logged. Caught only by `fleet-turn-check`.
- **The kind mismatch (obligation 2).** Receipted `ok`, shown to nobody. Recurred after the
  fix was deployed; now gated.
- **The unbound mention (obligation 3).** Delivered to nobody, looks like a dead unit.
- **A config edit that was never loaded.** Rules load at start only. The corrected file sits
  unread while the symptom is re-debugged.
- **A malformed filter expression crash-loops the unit.** Filter compilation is *eager*, so
  a bad expression is not a rule that silently never matches — it is a unit that will not
  stay up. That is the safe direction, and it is why an edit here is a restart, not a reload.
- **Journal silence read as evidence.** `buzz-agent@*` logs lifecycle only — start,
  shutdown, subscribe, reconnect — never a line per message. A silent journal during a live
  turn is the normal case. Prove work by `CPUUsageNSec` against an idle sibling.
- **Timestamp inversion.** buzz-acp logs UTC; `journalctl` renders CEST (+2). Correlating
  without normalising once made four pings look like they landed on a live service when they
  arrived after it had died.
- **The context ceiling, marcus only.** He is the DAG root with ~20 channels against 4–8 for
  the others, and the limit bounds *messages*, not tokens. `Prompt is too long` ×258. A
  restart resets it and it re-accumulates.
- **augustus's namespace.** His bwrap wrapper `--tmpfs`es `~/.ssh` and
  `~/.config/agent-workforce`, so he can never `git fetch` — which surfaced once as a bogus
  "origin unreachable". Never fix a capability gap here by widening the namespace; anything
  the bridge can read inside bwrap, his shell can read too.
- **Presence is not liveness.** A stale or Desktop-held relay presence ticks happily for a
  pubkey whose box unit is dead. Check `systemctl --user is-active` first.
