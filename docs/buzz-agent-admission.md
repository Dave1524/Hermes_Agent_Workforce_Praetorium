# Admitting `praetorium` — the prepared change

**Status: prepared, not applied.** Everything here is ready to run; none of it has been. It needs
a decision from Dave first, for the reasons in "Why this is not shipped".

## The problem

`bin/deliver.sh` publishes as the service identity `praetorium`
(`b0a6d15f871ab8c502029e57e0fddec3ddecb09846ffdf6a56b6515bd1906fcd`). Every rules file under
`~/.config/buzz-team/` admits exactly two authors:

| File | Admitted authors |
|---|---|
| `marcus.toml` | Dave (`82cfc202…616f`) |
| `claudius.toml`, `augustus.toml`, `trajan.toml` | Dave, and marcus (`abbc19dd…916b`) |

The units run `--subscribe config`, so those rules are the whole dispatch surface. praetorium
clears buzz-acp's NIP-OA sibling author gate — it is an agent of the same owner — and is then
dropped by the rules, which can only narrow.

**Consequence: no scheduled delivery can wake any agent, and none ever has.** Not for want of a
`p` tag, a channel, or an event kind — the author is refused before those are consulted. 20
receipts across 12 producers, 19 of them `delivered` with `buzz_result: ok`, and zero agent turns.
The receipts are honest: the message reached the channel. Nobody was listening.

This is invisible from every direction. `deliver.sh` gets an `ok` from the relay. The receipt says
`delivered`. The units log lifecycle only, so a dropped event leaves no line. The only tell is
that no agent has ever responded to a scheduled delivery, which reads as "the agents have nothing
to add" rather than as a wiring fault.

## The fix, in two halves

Both halves are required. Either alone changes nothing.

### Half 1 — admit the author (`~/.config/buzz-team/*.toml`)

Append to each of the four files:

```toml
[[rules]]
name = "praetorium"
channels = "all"
require_mention = true
filter = 'author == "b0a6d15f871ab8c502029e57e0fddec3ddecb09846ffdf6a56b6515bd1906fcd"'
```

`require_mention = true` is deliberate and matters more than it looks. `resolve_channel_filters`
(`crates/buzz-acp/src/config.rs`, `SubscribeMode::Config` arm) merges `require_mention` across
every rule that applies to a channel, and **any** rule with `require_mention = false` clears it for
that whole channel — not just for its own matches. One relaxed rule would widen the NIP-01
subscription for every author, so the agent would receive every message in the channel and drop
most of them at dispatch. Keeping it `true` means the delivery must name the agent, which is
half 2.

The expression is the same single-equality shape as the four filters already running; only the hex
literal differs. There is no offline validator — `buzz-acp` exposes no `--validate-config`, and
pointing it at a dead relay is a non-test, because `--config` rules load *after* the relay
connects. Shape-identity with a proven-working expression is the strongest check available short
of a live restart.

### Half 2 — name the agent (`bin/deliver.sh`)

`buzz messages send` takes `--mention <hex|npub>` (repeatable). `deliver.sh` passes none today, so
every delivery lands with no `p` tag and would still be dropped by `require_mention`.

Route ownership, to be added as `ROUTE_<key>_notify` alongside the existing route and kind lines:

| Route | Owner | Why |
|---|---|---|
| `ops` | marcus | chief of staff; the operational feed |
| `approvals` | marcus | the approval queue is his to triage |
| `research` | claudius | head of research |
| `bd` | claudius | owns bd-stall-radar and bd-followup-drafts |
| `signals` | claudius | owns the M1 signal scan |
| `content` | augustus | editor-in-chief |

trajan owns no route. That is not an oversight — no scheduled producer writes engineering output.
Admitting praetorium in `trajan.toml` still has a point: it lets a future producer address him
without a second config change under a deny-listed tree.

`bin/buzz_routes.env` currently states "no agent names, no pubkeys" in its header. That rule exists
to keep credentials out of a tracked file, and a pubkey is not a credential — but rather than
quietly reinterpret it, the notify map should carry **slugs** (`ROUTE_ops_notify=marcus`) with a
sibling `bin/buzz_agents.env` mapping slug to pubkey. Two files, one job each, and the routes file
keeps its property of naming no identity.

## Rolling it out

A malformed evalexpr filter **crash-loops the unit** — it does not fail lazily and it does not
degrade to mentions (that degradation is setup mode only). So:

1. One agent first. `claudius.toml` is the right pilot: it already carries two rules, so a third
   exercises the merge path, and it owns three routes.
2. Edit, then `systemctl --user restart buzz-agent@claudius`, then verify — as one step. A rules
   file is read only at start, so an unrestarted edit is untested, and `systemctl --user show
   buzz-agent@claudius -p ExecMainStartTimestamp` against the file's mtime is what proves it was
   read.
3. `systemctl --user is-active` and a 60-second watch for restart looping.
4. Prove dispatch by resource footprint, never by log lines: `systemctl --user show
   buzz-agent@claudius -p CPUUsageNSec` before and after a delivery, with an idle sibling as the
   control. buzz-acp logs nothing per message dispatched, so a silent journal is the normal case
   and is not evidence either way.
5. Only then the other three.

## Why this is not shipped

- **Half 1 changes agent dispatch fleet-wide.** 17 producers currently deliver into six routes
  with nothing listening. Admitting praetorium turns each of those into an agent turn. The static
  prompt layers are 27-32 KB and are resent on every request of a 20-47-request turn, so this is
  the single largest token-spend change available on this box, and it fires unattended overnight.
  That is Dave's call, not a side effect of a delivery fix.
- **It is a behaviour change disguised as a config edit.** Nothing in the diff says "every
  scheduled job now wakes an agent".
- **A wrong filter takes the unit down**, and these units are the interactive surface.

## While you are in those files

`claudius.toml`, `augustus.toml` and `trajan.toml` each carry this comment:

> filter compilation is LAZY — a malformed expression is silent at startup and then fails closed
> at dispatch

That is false, and it is the exact claim that would make someone edit a filter without watching
the restart. Compilation is eager; a malformed expression crash-loops the unit. Corrected
2026-08-07. The comment is inert, so it is not worth a restart of its own — fix it on the same
pass as the rule.
