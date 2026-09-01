# Agent model — surfaces, manifests, and what each agent may do (D2)

**Status: DRAFT 2026-09-01** — build-order step 2 of the approved infrastructure review
(Notion: "Proposal — Praetorium agent infrastructure review"). Starts from the frozen
`design/workflow-registry.md` (D1), which answers *which workflows exist and who is
accountable*. This file answers Dave's second question — **which actions, tools and
skills each agent requires** — and defines the manifest that makes the answer
enforceable rather than remembered.

Every claim below was read from live state on 2026-09-01, not from the repo's own
documentation. Where the repo and the live box disagree, §6 records which is which.

## 1. The finding this document exists for

"Which tools does agent X have?" has **no single answer on this box**, because every
persona runs on more than one execution surface and each surface has a different tool
set, governed in a different file, written by a different mechanism. Nothing today
states any agent's full capability in one place. That is the design gap D2 closes.

Concretely, claudius is four different things depending on how you reach him:

- over Buzz he has Claude Code's full built-in toolset, qmd over MCP, seven Notion
  tools through the broker, and — unintentionally — Gmail, Outlook and Drive;
- inside `knowledge-digest` he has exactly `Bash,Read,Write,Edit,Glob,Grep` and **no
  MCP server at all**;
- inside `m1-signal-scan` he additionally has `WebSearch,WebFetch`;
- on a kanban card he has the Hermes toolset plus a 30-entry skills allowlist.

None of those four facts is derivable from the other three, and no file names them
together. A capability decision ("claudius may not act outward") is therefore made
four times, in four syntaxes, and can silently hold in three places while failing in
the fourth. §6.1 is exactly that failure, live today.

## 2. The four execution surfaces

| # | Surface | Runtime | Who runs here | Tool set | Governed by |
|---|---|---|---|---|---|
| **S1** | Buzz interactive | `claude-agent-acp` (marcus, claudius, trajan, aurelian); `codex-acp` in bwrap (augustus) | all five personas | Claude Code built-ins + `mcp__qmd-mcp__*` + 7 `notion_*` (broker) + **whatever `~/.claude/settings.json` does not deny** | `~/.config/systemd/user/buzz-agent@.service` (flags), `~/.config/buzz-team/<name>.toml` (who may wake whom), `~/.claude/settings.json` (`permissions.deny`) |
| **S2** | Scheduled headless CC | `claude -p` from `bin/run_*_cc.sh`, wrapped by `bin/agent_propose.sh` | nobody — the owner persona is *accountability*, the executor is anonymous | explicit `--allowedTools`; **no MCP** (`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`) | the wrapper script, one per workflow, in `bin/` |
| **S3** | Hermes kanban dispatch | `hermes-gateway` auto-dispatches `ready` cards every 60s | marcus, claudius, augustus, trajan (profiles on disk). **Not aurelian** | Hermes toolsets + a real skills index with a per-profile allowlist | `~/.hermes/profiles/<p>/config.yaml`, written by `bin/apply_skills_allowlist.sh` |
| **S4** | Buzz-dispatched scheduled | `bin/run_content_via_buzz.sh` — a timer that triggers **S1** and waits | augustus only | inherits S1 entirely | `bin/buzz_routes.env` (destination, kind, who to wake) + the profile augustus is told to read |

**S2 is the surface that does nearly all the unattended work and it has no persona at
all** — `AGENT_PROFILE` carries a *model* name (`claude-sonnet`, `claude-opus`), which
is what causes registry inconsistency §6.6. The manifest is where the owner persona
becomes a real value that S2 can key on.

### Permission posture is uniform and permissive

All of S1, S2 and S4 run at `bypassPermissions` / `bypass-permissions`. Nothing is
gated at the tool-approval layer anywhere on this box. **Every real boundary is either
an allowlist (S2), a deny-list (S1), or prose in a charter.** Design accordingly: a
capability you do not want used must be *absent*, not *discouraged*.

### Skills are two mechanisms, and the bigger investment sits on the smaller surface

- **S1 and S2 have no skill index.** `~/.claude/skills/` does not exist. The only
  registered skills are the seven in the `shared@jbuitenhuis` plugin (`arch-audit`,
  `capture-learning`, `codex`, `ddd-design`, `quality-check`, `task-manage`,
  `task-triage`). The vault's **32** `08_skills/*/SKILL.md` are markdown reachable by
  path or qmd — an agent reads them, nothing offers them.
- **S3 has a real skill index**: 148 `SKILL.md` across nine `~/.hermes/shared-skills/`
  subdirectories, with `skills.external_dirs` + `skills.disabled` applied per profile.
  Measured 2026-09-01 — offered counts are **marcus 46, trajan 44, claudius 25,
  augustus 23**. Note the two lists are disjoint: **`disabled` removes zero of the
  allowlisted skills** (0 name collisions on all four profiles — it suppresses Hermes's
  *bundled* set, `apple-notes`, `imessage`, `computer-use` and friends). So the effective
  offering is exactly the `external_dirs` total; `disabled` is a separate hygiene list and
  should not be read as narrowing the allowlist.

So the NUC-42 skills-allowlist work governs **only S3**, which D1 §7.6 just reduced to
a queue for one-offs. This is not a bug — but it means "which skills per agent" has a
precise answer only on the surface that now carries the least work, and a *positional*
answer ("whatever is on disk at a path the agent happens to read") everywhere else.
**Deciding what to do about that is §8, decision 3.**

## 3. What a manifest is

One file per persona: `design/agents/<name>.toml`. It is the single normative statement
of what that agent is, owns, may do and may not do — **across all four surfaces**.

TOML rather than YAML or JSON, for two box-specific reasons: `tomllib` is in the Python
3.14 stdlib here while **PyYAML is not installed**, so a validator can parse TOML with
no dependency; and comments survive, which this repo's conventions depend on.

A manifest is **descriptive today and normative after Phase B**. It is written to be
the source that generates, rather than duplicates:

| Consumer | What it takes from the manifest | Replaces |
|---|---|---|
| `AGENT_PROFILE` in each job env | `owner` | six model-named values (registry §6.6) |
| `--allowedTools` in `bin/run_*_cc.sh` | `surfaces.scheduled.tools` | 11 hand-written strings |
| coverage lists in the reporting jobs | `workflows[].unit` | the `praetorium-*` glob defect in six files (registry §6.4) |
| D3 eval targets | `workflows[]` + `must_not` | a hand-kept list that does not exist yet |

Until a generator exists these are *aspirations*, and §7 says so plainly.

## 4. Manifest schema

```toml
name        = "claudius"          # persona slug; matches the Buzz identity and (S3) the hermes profile dir
role        = "..."               # one line, the accountable role from D1 §1
pubkey      = "..."               # Nostr identity, public by construction (bin/buzz_agents.env)
harness     = "claude-agent-acp"  # or "codex-acp"
status      = "live"              # live | read-only | retired

[surfaces.<interactive|scheduled|kanban|buzz_dispatch>]
present     = true                # false = this persona does not exist on this surface
governed_by = "path"              # the ONE file that decides the below
tools       = [...]               # what it may call HERE
mcp         = [...]               # MCP servers reachable HERE ([] = --strict-mcp-config)
admits      = [...]               # interactive only: whose mentions this agent answers
skills      = 25                  # kanban only: offered count, measured
notes       = """..."""

[[workflows]]                     # one per workflow this persona OWNS (D1 §2/§3/§4)
unit        = "knowledge-digest"  # systemd unit, no suffix — the join key to systemd
surface     = "scheduled"
trigger     = "Sun 09:00 (+5min jitter)"   # DECLARED OnCalendar, never next-elapse (§6.8)
model       = "claude-opus-5"
profile     = "profiles/..."      # the task prompt
runner      = "bin/run_*.sh"      # what actually execs
route       = "research"          # key in bin/buzz_routes.env, or omitted
contract    = "design/contracts/knowledge-digest.md"
status      = "planned"           # omit when live
alerted     = true                # platform jobs: is OnFailure present ON THE LIVE UNIT
in_repo     = false               # is there a source unit in systemd/ at all (§6.7)
notes       = """..."""

[[must_not]]                      # one block per prohibition
rule        = "send email or any outward message"
enforced    = false               # true = a mechanism blocks it TODAY
why         = "charter; §6.1 leaves Gmail/M365 live on the interactive surface"
```

`must_not` is the field that earns the file. Today "claudius must not act outward" is
prose in a charter that S1's deny-list does not enforce (§6.1). Stated here once, a
Phase-B validator can assert it against every surface at once — and `enforced = false` is
the honest half: it marks a rule that is policy, not mechanism, instead of implying a
boundary that does not exist.

`must_not` must be an **array of tables**, not an inline array placed after a `[[workflows]]`
block — TOML would scope it into that workflow. Every manifest here parses under `tomllib`;
the first Phase-B test asserts that it still does.

Live totals: 26 workflows across five manifests — marcus 4, claudius 6 (4 live + 2 planned
per registry §7.5), augustus 4, trajan 12, aurelian 0 (by design, §6.4).

## 5. Governance rules

1. **The manifest names the owner; the registry names the workflow.** A workflow
   appears in `design/workflow-registry.md` and its owner's manifest, and nowhere else
   claims ownership. Two claims is the defect, not a redundancy.
2. **A capability is added on one surface at a time, and the manifest says which.**
   Adding `WebSearch` to a scheduled wrapper does not grant it on Buzz and must not be
   described as "claudius can search the web".
3. **A prohibition must name its enforcement point.** A `must_not` entry with no
   corresponding allowlist absence or deny-list rule is an aspiration; mark it
   `enforced = false` rather than implying a boundary that does not exist.
4. **Deployed-copy convention (D1 §7.8) still holds**: units ExecStart from
   `~/agent-workforce/bin` except auto-sync. The manifest records the source path; the
   runtime reads the deployed one.

## 6. Live gaps found while writing this

Each was read from the running box on 2026-09-01, with the evidence named.

### 6.1 Outward-action tools are live in every Buzz agent session

`claude-agent-acp` starts each session with `settingSources: ["user","project","local"]`
(`…/claude-agent-acp/dist/acp-agent.js:4156`), and agents run with cwd `/home/dave`, so
**`~/.claude/settings.json` governs all five agents**. Its `permissions.deny` blocks
`mcp__claude_ai_Notion` — correctly, per Dave's REST-only directive — and blocks the
four secret paths. It denies **nothing else**.

Live in this session, therefore live in every agent session:
`mcp__claude_ai_Gmail__send_message`, `mcp__claude_ai_Microsoft_365__outlook_send_mail`,
`mcp__claude_ai_Google_Drive__share_file`, plus the rest of Gmail, M365, Drive and Figma.

The charter says the fleet drafts and never acts outward. On S2 that is true by
construction — those tools are not in any `--allowedTools`. On S1 it is true only
because the agents have not tried. **The deny-list is one line per connector and the
mechanism is already proven** (the Notion deny dropped its tools mid-session,
2026-08-03). This is the highest-value, lowest-cost item in D2.

### 6.2 The failure-alert throttle has been deployed but unwired for 18 days

`cf85dbe` (2026-08-14) moved the `OnFailure` handler out of the unit file into
`bin/agent_alert.sh`, whose whole purpose is to stop repeat alerts — its header cites a
stuck `qmd-refresh` emitting 14 identical alerts on 2026-08-14. `bin/deploy` copied the
script (`~/agent-workforce/bin/agent_alert.sh`, mtime 08-14 19:05). **The unit was never
installed to `/etc`**: `/etc/systemd/system/agent-alert@.service` is dated 2026-08-07 and
still carries the old inline `/bin/sh -c` handler, which is what `systemctl cat` shows
loaded right now.

Measured cost: of the last 60 lines of `~/logs/agent-alert.log`, **19 are `qmd-refresh`**
— precisely the repetition the fix removes. The fix exists, is deployed, and is
unreachable. This is the "unit-file change deploys INERT" trap caught in the wild, with
an 18-day dwell. Phase-B fix is one `sudo cp` plus `daemon-reload`.

### 6.3 Repo unit files are behind `/etc`, not ahead of it

Diffing `systemd/*.service` against `/etc/systemd/system/`, four differ.
Three — `bd-stall-radar`, `m1-signal-scan`, `weekly-pre-assembly` — differ only in that
**`/etc` has `OnFailure=agent-alert@%n.service` and the repo does not.** Somebody added
alerting live and never back-ported it. The fourth is §6.2, drifting the other way.

Two consequences. First, `systemd/` is not a reliable picture of what is installed, in
either direction — check `systemctl cat`, never the repo file. Second, **this corrects
`.claude/briefs/bd-radar-followup-timers.md`**, which lists "add the missing `OnFailure`"
as a fix for `bd-stall-radar.service`. The repo edit is still right; the brief's framing
— implying live runs unalerted — is wrong. Live has had it all along.

Genuinely missing on the live box, all platform jobs: `fleet-eval`, `local-tier-eval`,
`memory-consolidation`, `scorecard`. Under D1 §7.1 those are **trajan's**.

### 6.4 One persona's manifest has no Buzz identity to point at

`aurelian` has a `~/.config/buzz-team/aurelian.toml` and a live unit, but **no entry in
`bin/buzz_agents.env`** — the four slugs there are marcus, claudius, augustus, trajan.
That is correct today (no route may address him; he is a sink), and the manifest records
it as deliberate rather than leaving the next reader to wonder.

### 6.5 The two content-research timers expire BY DESIGN — do not make them recurring

**This section originally claimed both workflows were about to fail silently and needed a
one-line recurring-calendar fix. That was wrong, and the fix would have been harmful. The
finding is retained, inverted, because the mistake is the instructive part.**

What is mechanically true: `praetorium-content-strategy-research.timer` and
`praetorium-faceless-content-research.timer` carry four **absolute** `OnCalendar` lines each,
last firing 2026-09-03 23:00 and 2026-09-04 01:30, after which each has no next elapse and
stops. Everything above that line was read from `systemctl cat` and is correct.

What is false is the conclusion. Reading the units' own **comment headers** — which I did not
do before writing the first version — settles it:

> Explicit per-night `OnCalendar` lines, not a recurring pattern, to guarantee exactly 4
> firings and then stop on its own — same convention as the original.

These are **bounded research campaigns**, not standing workflows. Dave authorised six nights
each on 2026-08-14 (via the marcus Buzz relay, thread `8364eb54…`) on two named topics — 2026
content strategy, and faceless content as a digital product — to run while he was away. The
2026-08-27 OAuth outage killed four nights of each; `Persistent=true` does not re-fire a slot
that fired and failed, so on 2026-08-31 they were rescheduled for four make-up nights. Both
campaigns are **healthy and mid-run** as of 2026-09-01: content-strategy last ran 08-31 23:00
`OK`, next 09-01 23:00; faceless last ran 09-01 01:30 `OK`, next 09-02 01:30.

Converting them to `OnCalendar=*-*-* 23:00` / `*-*-* 01:30` would therefore not preserve a
capability — it would **create two permanent nightly Opus research jobs Dave never asked
for**, on topics already researched eight times each, and it would pin
`faceless-content-research` permanently at 01:30 against `augustus-content.timer` on the same
minute through the single global propose lock of §6.6 — a collision already observed live
(`2026-08-31T12:24:37 SKIP: previous run still active`).

**Correct posture: leave both timers alone and let them expire.** Whether a *standing*
content-research workflow should exist is a separate product decision for Dave, and if the
answer is yes it needs its own topic rotation, its own slot (not 01:30) and its own registry
row — not a one-line edit to a spent campaign.

**Generalisable trap — a finite schedule is not evidence of a defect.** "No next elapse after
date X" and "correctly-scoped one-shot campaign" are the same signal in `systemctl cat`. The
only thing that separates them is intent, and intent was written in the unit's comment header
the whole time. I read the `[Timer]` stanza and skipped the twelve lines above it. Before
calling any schedule broken, read the unit's own comments and the journal for what it has
been *producing* — a job doing exactly what it was built to do looks identical to one dying.
Same class as the registry's next-elapse error in §6.8: both came from reading one mechanical
field and not the object around it.

### 6.6 One global propose lock, and its collision exits 0 in silence

`bin/agent_propose.sh:26` defaults to `LOCK="${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}"`
— **one lock for every job that does not override it** — and `:144` is
`flock -n 9 || { log "SKIP: previous run still active"; exit 0; }`. Deliberately silent, and
correct for its intended case (timer overlap of the *same* job). Across *different* jobs it
means a scheduled workflow can be dropped entirely with a success exit, no proposal, and no
alert — indistinguishable from a healthy night.

Demonstrated live: `praetorium-faceless-content-research` logged
`2026-08-31T12:24:37+02:00 SKIP: previous run still active` and deactivated successfully.
One occurrence in 14 days, so the mechanism is proven, not theoretical.

The standing exposure is worse than that one hit suggests: **`augustus-content.timer` and
`praetorium-faceless-content-research.timer` both fire at 01:30**, and `augustus-content`
carries `RandomizedDelaySec=5min`, which is exactly what makes the overlap intermittent
rather than nightly. Whether they currently share the lock cannot be read from here — the
`AGENT_PROPOSE_LOCK` override, if any, lives in the deny-listed `augustus-content.env`. The
manifest therefore records the lock as a per-workflow field so the answer stops being
unreadable, and Phase B should give every workflow a slug-derived lock by default rather
than an opt-out global one.

### 6.7 Four live units exist only in `/etc` and are in no repo

Diffing every non-OS unit in `/etc/systemd/system` against `systemd/` and `systemd/archive/`:
**`fleet-turn-check`, `ttm-pool-drain`, `praetorium-content-strategy-research` and
`praetorium-faceless-content-research`** (service + timer each) have no source anywhere in
this repo. Two are trajan's platform jobs, two are augustus's persona workflows. They are
unreviewed, unversioned, and would not survive a rebuild — and §6.5 is a defect in one of
them that a repo diff would have caught in review.

Together with §6.2 and §6.3, `systemd/` now has three distinct relationships to reality:
ahead of `/etc` (agent-alert), behind it (three OnFailure lines), and absent from it (these
four). Treat the repo as a partial mirror, never as an inventory.

### 6.8 Registry §2 recorded next-elapse times, so three schedules are wrong by day

Every trigger in `design/workflow-registry.md` §2 is a *next-elapse* value, which folds in
`RandomizedDelaySec` and shows only the next occurrence. Compared against the declared
`OnCalendar`:

| Unit | Registry §2 says | Declared |
|---|---|---|
| agent-proposal (standing research) | daily 04:31 | **Mon..Fri** 04:30 (+5min) |
| raw-ingest | daily 03:00 | **Tue..Sat** 03:00 (+5min) |
| m1-signal-scan | daily 05:30 | **Mon,Wed** 05:30 (+5min) — twice weekly |

The minute-level drift (06:01 for 06:00, 22:19 for 22:15) is harmless jitter. The day
specs are not: m1-signal-scan is recorded as running seven times a week and runs twice,
and `CLAUDE.md` has had the correct values all along. Anything that reasons about expected
run counts — a scorecard, a "0 error runs in 7d" claim, a D3 eval cadence — inherits the
error. The manifests carry the declared values; the registry has a correction footnote.

**General rule adopted for D2 and D3: read a schedule from `systemctl cat`, never from
`list-timers`.** One tells you what was asked for, the other what happens to be next.

## 7. What is inert until Phase B — stated plainly

The five manifests in `design/agents/` are **documentation until a consumer reads them**.
Nothing generates `--allowedTools` from them, nothing validates them, nothing fails if a
wrapper and its manifest disagree. Writing them is D2; wiring them is Phase B, and the
first brief should be the validator, because a manifest that can drift from the box
silently is worth less than no manifest at all.

The minimum wiring that makes them load-bearing, in the order it should be built:

1. `tests/test_agent_manifests.sh` — every manifest parses; every workflow in
   `design/workflow-registry.md` §2/§4 is claimed by exactly one manifest; every
   `surfaces.scheduled.tools` matches the `--allowedTools` of the named wrapper. Hooks
   into `bin/verify.sh`, which already runs `tests/*.sh`.
2. The `AGENT_PROFILE` → owner rename (registry §6.6), taking its values from `owner`.
3. Generated coverage lists for the reporting jobs (registry §6.4).

## 8. Decisions required from Dave

1. **Close §6.1 by denying the outward connectors in `~/.claude/settings.json`?**
   Recommended yes — Gmail, M365, Drive and Figma, one deny line each. It costs nothing
   the fleet uses today and makes "drafts only" true rather than merely instructed.
   Note it applies to *Dave's own interactive sessions on this box too*, since there is
   one settings file; a split policy needs a wrapper injecting `--settings`.
2. **WITHDRAWN 2026-09-01.** This asked for a timer fix before 2026-09-03. §6.5 was wrong:
   both content-research timers are bounded campaigns and expire by design. No action. The
   live question it *should* have asked is now decision 6 below.
3. **Fix §6.2 and §6.3 now, or fold them into the Phase-B bd-radar brief?**
   Recommended: fix §6.2 now (it is degrading alerting today), fold §6.3 in. §6.6 and §6.7
   are Phase B — per-workflow locks, and importing the four orphan units into `systemd/`.
4. **Skills posture.** S1/S2 have no skill index and 32 vault skills reachable only by
   path. Options: (a) leave as is — agents read the vault, which works; (b) register the
   role-relevant vault skills as Claude Code skills so they are *offered* rather than
   remembered; (c) retire the S3 allowlist investment now that hermes is a one-off queue.
   These are not exclusive. Recommended (b) for the four skills the content and research
   workflows actually name, and leave (c) alone until a card actually fails.
5. **Confirm the manifest is the source of truth** for tools/owner/coverage, i.e. that
   Phase B may generate the wrappers' `--allowedTools` from it rather than the reverse.
6. **Do you want a *standing* content-research workflow at all?** (Replaces the withdrawn
   decision 2.) The two campaigns end 09-03 and 09-04 having delivered ~8 runs each on two
   named topics. A permanent version is a different thing and needs its own topic rotation,
   a slot that is not 01:30 (the augustus-content collision of §6.6) and its own registry
   row. Recommended: **no** for now — let them expire, and revisit once the content
   pipeline's existing backlog is consumed.
