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

Concretely, claudius was four different things depending on how you reach him, and is
now three:

- over Buzz he has Claude Code's full built-in toolset, qmd over MCP, and seven Notion
  tools through the broker — and, until 2026-09-01, Gmail, Outlook and Drive as well
  (§6.1, now closed);
- inside `knowledge-digest` he has exactly `Bash,Read,Write,Edit,Glob,Grep` and **no
  MCP server at all**;
- inside `m1-signal-scan` he additionally has `WebSearch,WebFetch`;
- on a kanban card he had the Hermes toolset plus his hermes profile's 25-skill
  offering (§3) — **S3 retired 2026-09-02 (D7)**.

None of those facts is derivable from the others, and no file names them together. A
capability decision ("claudius may not act outward") is therefore made three times — it
was four — in as many syntaxes, and can silently hold in two places while failing in the
third. §6.1 is exactly that failure, live today.

**Retirement did not weaken this finding. It is the finding.** The fourth bullet sat here
describing a live capability for the six weeks after the board's last card completed
(2026-07-20), because nothing joined "claudius has a toolset here" to "anything still
dispatches here". A capability statement with no liveness check outlives its surface and
reads identically either way — which is the same defect class D8 found in the deploy gate
and §6.1 found in the connector deny-list. **S4 keeps its number**: the identifiers name
surfaces, not positions in a count.

That fourth bullet also said *"a 30-entry skills allowlist"* until 2026-09-02. It was
never a 30-entry allowlist: 30 is claudius's 3 `skills.external_dirs` plus 27
`skills.disabled`, and §3 records those as disjoint mechanisms — the second is a deny
list. The offered count is 25.

## 2. The four execution surfaces — three live since 2026-09-02

S3 is retired but keeps its identifier and its row. The identifiers name surfaces, not
positions in a count, and a table that renumbers on retirement silently invalidates every
"S4" written before the edit.


| # | Surface | Runtime | Who runs here | Tool set | Governed by |
|---|---|---|---|---|---|
| **S1** | Buzz interactive | `claude-agent-acp` (marcus, claudius, trajan, aurelian); `codex-acp` in bwrap (augustus) | all five personas | Claude Code built-ins + `mcp__qmd-mcp__*` + 7 `notion_*` (broker) + **whatever `~/.claude/settings.json` does not deny** | `~/.config/systemd/user/buzz-agent@.service` (flags), `~/.config/buzz-team/<name>.toml` (who may wake whom), `~/.claude/settings.json` (`permissions.deny`) |
| **S2** | Scheduled headless CC | `claude -p` from `bin/run_*_cc.sh`, wrapped by `bin/agent_propose.sh` | nobody — the owner persona is *accountability*, the executor is anonymous | explicit `--allowedTools`; **no MCP** (`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`) | the wrapper script, one per workflow, in `bin/` |
| ~~**S3**~~ | ~~Hermes kanban dispatch~~ — **RETIRED 2026-09-02 (D7)** | ~~`hermes-gateway` auto-dispatches `ready` cards every 60s~~; the gateway is disabled+stopped, the board is archived (`design/archive/hermes-kanban-board.md`), `bin/kanban_run_and_wait.sh` is deleted | ~~marcus, claudius, augustus, trajan~~ — nobody | ~~Hermes toolsets + a real skills index with a per-profile allowlist~~ | `~/.hermes/profiles/<p>/config.yaml` and `bin/apply_skills_allowlist.sh` **both survive** — the CLI still reads them (§3) |
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
- **The hermes profiles have a real skill index**: 148 `SKILL.md` across nine
  `~/.hermes/shared-skills/` subdirectories, with `skills.external_dirs` +
  `skills.disabled` applied per profile. Measured 2026-09-01 — offered counts are
  **marcus 46, trajan 44, claudius 25, augustus 23**. Note the two lists are disjoint:
  **`disabled` removes zero of the allowlisted skills** (0 name collisions on all four
  profiles — it suppresses Hermes's *bundled* set, `apple-notes`, `imessage`,
  `computer-use` and friends). So the effective offering is exactly the `external_dirs`
  total; `disabled` is a separate hygiene list and should not be read as narrowing the
  allowlist.

  **These are profile facts, not S3 facts, and that distinction is why they survive
  2026-09-02.** The index is resolved per `~/.hermes/profiles/<p>/`, and a profile is
  reachable from any `hermes -p <profile>` invocation — S3 was one caller, and it is not
  the last one: `bin/local_tier_eval.sh:105` runs `-p marcus` six times a day. Do not
  relocate these counts into an S1/S2 claim, where the bullet above records that no skill
  index exists at all; a number moved somewhere it is false is worse than a number with a
  retired owner.

So the NUC-42 skills-allowlist work governed **only S3**, and S3 is retired
(2026-09-02, D7). The measurement that settles what it was worth is in
`design/archive/hermes-kanban-board.md`: **0 of the board's 11 cards ever carried a
non-empty `skills` field.** The allowlist mechanism was never exercised once from the
only surface that offered it. So "which skills per agent" now has a precise answer on
**no** surface at all, and a *positional* answer ("whatever is on disk at a path the
agent happens to read") everywhere — which is a cleaner statement of the same gap, not
a new one.

That is an argument for deciding §8.4 deliberately, not for deleting the mechanism.
`bin/apply_skills_allowlist.sh` writes the config a live platform job reads; whether the
allowlist affects a `-z` oneshot is **unverified**, and "S3 is gone" is not evidence
either way.
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
name        = "claudius"          # persona slug; matches the Buzz identity and the hermes
                                  # profile dir — the latter outlived S3's retirement
role        = "..."               # one line, the accountable role from D1 §1
pubkey      = "..."               # Nostr identity, public by construction (bin/buzz_agents.env)
harness     = "claude-agent-acp"  # or "codex-acp"
status      = "live"              # live | read-only | retired

[surfaces.<interactive|scheduled|kanban|buzz_dispatch>]
present     = true                # false = this persona does not exist on this surface
retired     = "2026-09-02"        # optional: the SURFACE is gone, not just this persona's
                                  # place on it. Set on all five `kanban` blocks by D7.
                                  # `present = false` alone cannot say which of the two it
                                  # means — aurelian's kanban block was already false while
                                  # the surface was live.
governed_by = "path"              # the ONE file that decides the below
tools       = [...]               # what it may call HERE
mcp         = [...]               # MCP servers reachable HERE ([] = --strict-mcp-config)
admits      = [...]               # interactive only: whose mentions this agent answers
skills      = 25                  # kanban blocks only: the offered count of the hermes
                                  # PROFILE named by governed_by, measured. Outlives the
                                  # retired surface — see §3 before moving this number.
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
status      = "standing"          # REQUIRED on every entry — see the table below (R15)
expires     = "2026-09-03 23:00"  # campaign only: the last absolute OnCalendar date
alerted     = true                # platform jobs: is OnFailure present ON THE LIVE UNIT
in_repo     = false               # is there a source UNIT FILE in systemd/ at all (§6.7)
suite       = ["tests/test_knowledge_digest_smoke.sh"]   # REQUIRED on every entry (R15b)
suite_exempt = "script lives outside this repo at <path>" # presence = exempt from needing a suite
notes       = """..."""

[[must_not]]                      # one block per prohibition
rule        = "send email or any outward message"
enforced    = true                # D9: true iff a machine-checkable artifact exists whose
                                  # removal or absence a test can DETECT. Not "a mechanism
                                  # blocks it" in the abstract — see eval-spec.md §7.4.
why         = "<the mechanism, named precisely enough to be wrong>"
test        = "tests/test_fleet_guards.sh::connector-deny"  # REQUIRED when enforced = true
test_exempt = "mechanism is a surface that no longer exists" # presence = exempt from needing a test
```

### Workflow `suite` — required on every entry (R15b)

`suite` is a **hand-declared** list of the test files that own this workflow. It is declared,
not inferred, because inference does not work: D6 measured four plausible join rules
(unit-name-in-suite-text, suite-filename-matches-unit, the `runner` field, `runner` plus
wrapper-chain resolution) and got four different coverage numbers, with false greens and false
reds in both directions. Three reasons no rule survives:

- **13 of 26 entries carry no `runner`** — every trajan platform job — so that key is
  unavailable for half the registry.
- **Coverage can sit three hops out.** `agent-inbox-sync` -> `bin/agent_inbox_pipeline.sh` ->
  `bin/agent_inbox_notion_sync.py` -> `tests/test_agent_inbox_body_sync.sh`.
- **Two workflows can share one implementation.** `praetorium-daily-plan` and
  `praetorium-eod-summary` both run `bin/run_daily_rhythm_cc.sh`; resolving the wrapper chain
  far enough to find either suite is far enough to credit each job with the other's.

Rules:

- `status = "standing"` and no `suite_exempt` => `suite` must be non-empty.
- Every path in `suite` must exist on disk. A checker asserts this; a stale path is the
  failure mode a declared join trades for an inferred one, and it is the cheap one.
- `suite_exempt = "<reason>"` marks a workflow whose code is not in this repo. It is a
  **separate field from `in_repo`** on purpose: `in_repo` describes the *unit file*
  (`ttm-pool-drain` is `in_repo = true` since D2 adopted its unit into `systemd/`), while its
  *script* is `/usr/local/bin/ttm-pool-drain` and is not here. One word, two referents.
- Exempt is not hidden. The checker prints every exempt workflow by name on each run —
  `fleet-turn-check` is the gate that proves an agent can complete a turn, and a silent
  exemption is how that kind of thing stops being looked at.

### Workflow `status` — required on every entry (R15)

`status` was previously "omit when live", which made absence carry meaning and left a
coverage checker unable to tell an untested standing job from a campaign that was always
meant to stop. It is now mandatory on all 26 entries. The vocabulary is the one this
design already used in prose, and the last column is the whole reason the field exists:

| value | means | on the box | needs an owning suite? |
|---|---|---|---|
| `standing` | recurring, enabled, no end date | timer enabled, next elapse in future | **yes** |
| `campaign` | bounded run; a finite list of absolute dates | enabled, `expires` still ahead | no — assert `expires` is future |
| `spent` | every date has fired; no next elapse | inert clutter, should be removed | no — flag for removal |
| `dormant` | unit files installed, timer **disabled** | present in `/etc`, not enabled | no — assert still disabled |
| `planned` | decided; no unit files on the box | nothing installed | no |

Deliberately different words from the agent-level `status` (`live | read-only | retired`),
so a grep for one never matches the other.

Three rules follow:

1. **`campaign` requires `expires`.** A bounded job with no stated end is how §6.5 nearly
   became a "fix the timer" brief for a job that was expiring on purpose.
2. **A status is a claim about the box and is checked against it, not against this file.**
   The `dormant` entries here were written as `planned` / "timer not yet installed"; both
   units turned out to be fully installed in `/etc` and merely disabled. Read
   `systemctl is-enabled` before writing a status.
3. **Two entries sharing a `contract` are one workflow.** `augustus-content` and
   `content-change-dispatch` are two triggers on one workflow and point at one contract
   file, so 26 entries resolve to 25 workflows. They are the only such pair today.

   But do not build the dedup on `contract` alone: **only 14 of the 26 entries carry a
   `contract` field at all.** Trajan's 12 platform jobs carry none, so the 14 resolve to 13
   distinct paths and the other 12 resolve to nothing. `contract-schema.md` says "the
   remaining 25 workflows carry a `contract` pointer to a file that does not exist yet" —
   that is true of 13, not 25, and was written before the platform jobs were enumerated.
   Whether a deterministic platform job should have a contract was parked here for D6,
   since a coverage checker has to decide what it does with an entry that names no
   contract. **ANSWERED 2026-09-02: the checker does not require `contract`, and a
   platform job does not need one.** Coverage is suite ownership; contracts are D3's
   acceptance-check layer, and the two are separate questions about a workflow. Only 14 of
   the 26 entries carry a contract, trajan's 12 platform jobs carry none, and that is
   correct rather than a backlog — a deterministic job's promise is liveness and an
   artifact, which a suite asserts, not output quality, which is what a contract grades.
   `tests/test_workflow_coverage.sh` therefore never reads the field.

Note for whoever writes the checker: **do not read liveness from `NextElapseUSecRealtime`.**
It is empty for every `OnUnitActiveSec` timer (monotonic, not realtime), and
`NextElapseUSecMonotonic` reads `infinity` for the seconds a timer is mid-trigger —
`ttm-pool-drain` showed exactly that during this audit and is entirely healthy. Use
`is-enabled` plus `LastTriggerUSec`.

`must_not` is the field that earns the file. It was written when "claudius must not act
outward" was prose in a charter that S1's deny-list did not enforce (§6.1, closed
2026-09-01). Stated here once, a Phase-B validator asserts it against every surface at
once — `tests/test_fleet_guards.sh` now does exactly that — and `enforced = false` remains
the honest half: it marks a rule that is policy, not mechanism, instead of implying a
boundary that does not exist.

`must_not` must be an **array of tables**, not an inline array placed after a `[[workflows]]`
block — TOML would scope it into that workflow. Every manifest here parses under `tomllib`;
the first Phase-B test asserts that it still does.

Live totals: 26 entries across five manifests — marcus 4, claudius 6, augustus 4, trajan 12,
aurelian 0 (by design, §6.4) — resolving to **25 workflows** and, by status: 22 `standing`,
2 `campaign`, 2 `dormant`, 0 `planned`, 0 `spent`. The two `dormant` are claudius's BD pair,
which §7.5 recorded as "planned"; they are installed and disabled, not absent.

## 5. Governance rules

1. **The manifest names the owner; the registry names the workflow.** A workflow
   appears in `design/workflow-registry.md` and its owner's manifest, and nowhere else
   claims ownership. Two claims is the defect, not a redundancy.
2. **A capability is added on one surface at a time, and the manifest says which.**
   Adding `WebSearch` to a scheduled wrapper does not grant it on Buzz and must not be
   described as "claudius can search the web".
3. **A prohibition must name its enforcement point, and `enforced = true` must name the
   test that detects its removal.** A `must_not` entry with no corresponding allowlist
   absence or deny-list rule is an aspiration; mark it `enforced = false` rather than
   implying a boundary that does not exist. Where a mechanism does exist, `test` names the
   assertion covering it (`<file>::<assertion-id>`), or `test_exempt` says in prose why no
   assertion is possible. `tests/test_fleet_guards.sh` enforces this rule on the manifests
   themselves, in both directions. Definition and rationale: eval-spec.md §7.4 (D9).
   **Same rule, different agents, different mechanism — name the right one.** marcus and
   claudius are covered by the strict settings file; augustus is covered by a harness that
   never had the connectors, and that file never reaches him. Attributing a real boundary
   to the wrong thing is the §6.1 defect in miniature, and it survives the removal of
   whatever actually held the line.
4. **Deployed-copy convention (D1 §7.8) still holds**: units ExecStart from
   `~/agent-workforce/bin` except auto-sync. The manifest records the source path; the
   runtime reads the deployed one.

## 6. Live gaps found while writing this

Each was read from the running box on 2026-09-01, with the evidence named.

### 6.1 Outward-action tools are live in every Buzz agent session — CLOSED 2026-09-01

`claude-agent-acp` starts each session with `settingSources: ["user","project","local"]`
(`…/claude-agent-acp/dist/acp-agent.js:4156`), and agents run with cwd `/home/dave`, so
**`~/.claude/settings.json` governs all five agents**. Its `permissions.deny` blocks
`mcp__claude_ai_Notion` — correctly, per Dave's REST-only directive — and blocks the
four secret paths. It denies **nothing else**.

Live in this session at the time of the audit, therefore live in every agent session:
`mcp__claude_ai_Gmail__send_message`, `mcp__claude_ai_Microsoft_365__outlook_send_mail`,
`mcp__claude_ai_Google_Drive__share_file`, plus the rest of Gmail, M365, Drive and Figma.
(That reading is the finding, not the current state — see the closure below.)

The charter says the fleet drafts and never acts outward. On S2 that was true by
construction — those tools are not in any `--allowedTools`. On S1 it was true only because
the agents had not tried.

**Closed 2026-09-01 (D1).** All four families are denied for agent sessions, and Dave's own
interactive sessions are unchanged — `~/.claude/settings.json` was not edited. The split is
the mechanism: `buzz-agent@.service` sets
`CLAUDE_CODE_EXECUTABLE=%h/.config/buzz-team/claude-agent-wrapper.sh`, and the wrapper
execs the real `claude` with `--settings ~/.config/buzz-team/agent-settings.json`, a
15-entry **superset** of the base deny list. Two things about that seam are load-bearing
and neither is guessable: `--settings` passed through `BUZZ_ACP_AGENT_ARGS` is a silent
no-op, because buzz-acp parses nothing from argv but `--version`; and the strict file is
written as a superset so the split holds whether the loader merges or replaces.

**It does not cover augustus, and must not be credited for him.** He runs `codex-acp`, so
the claude.ai connector surface is absent from his harness by construction — a separate
mechanism with its own assertion.

Asserted by `tests/test_fleet_guards.sh` (`::connector-deny`, `::deny-superset`,
`::augustus-no-claude-connectors`); `::deny-superset` is what goes red if a deny is ever
added to the base file and not mirrored here. Definition of the flag: eval-spec.md §7.4.

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

### 6.7 Live units exist only in `/etc` and are in no repo — CORRECTED, and CLOSED 2026-09-02

**The count was four families and it was three — `ttm-pool-drain` does not belong on this
list, and this same file contradicts it at line 167** (`in_repo = true` since D2 adopted its
unit into `systemd/`). The confusion is the one D6 already names: `in_repo` describes the
UNIT FILE, while ttm-pool-drain's *script* is `/usr/local/bin/ttm-pool-drain` and is not
here. One word, two referents. Measured 2026-09-02, the real list was three families / six
files: `fleet-turn-check`, `praetorium-content-strategy-research` and
`praetorium-faceless-content-research` (service + timer each).

**And it was never only `/etc`.** D8 named three unit trees; there are four. Nine `--user`
units in `~/.config/systemd/user/` had no source anywhere in this repo — including
`buzz-agent@.service`, the unit the whole Buzz fleet runs on, which brief 1 edited on
2026-09-01. `tests/test_fleet_guards.sh` asserts a line in it, so a rebuild from source
would have turned that guard red with nothing here to restore from.

Closed by brief 2 (D8): `fleet-turn-check.{service,timer}` backported byte-for-byte, the
nine `--user` units sourced at `systemd/user/`, and the two campaigns given dated exclusions
that expire on their own last firings. `bin/check_deploy_drift.sh` now asserts all of it in
both membership directions, so this section describes a closed defect rather than a standing
one — and the next instance goes red instead of being rediscovered by audit.

Together with §6.2 and §6.3, `systemd/` had three distinct relationships to reality: ahead of
`/etc` (agent-alert), behind it (three OnFailure lines), and absent from it. Treat the repo as
a partial mirror, never as an inventory — and note that "partial" was itself understated,
because a whole tree was missing from the comparison.

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
   ANSWERED yes, done 2026-09-01 as D1 — but **not** in `~/.claude/settings.json`, which
   was left untouched. The caveat in the original recommendation turned out to be the whole
   design: one settings file would have taken the connectors off Dave too, so the split
   runs through `CLAUDE_CODE_EXECUTABLE` and a wrapper that injects `--settings`. Mechanism
   and proof: §6.1.
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

   **(c) ANSWERED 2026-09-02 by D7, for the *offering* question only.** No card will ever
   fail, because there are no more cards — and the retirement measured the thing this
   decision was waiting on: 0 of the board's 11 cards ever set a non-empty `skills` field,
   so the allowlist was never exercised from a card in the surface's whole life. The S3
   *offering* is retired with the surface.

   **This is explicitly NOT licence to delete `bin/apply_skills_allowlist.sh` or
   `docs/skills_allowlist.md`.** They write and document
   `~/.hermes/profiles/<p>/config.yaml`, which `bin/local_tier_eval.sh:105` reads six
   times a day via `hermes -p marcus`. (a) and (b) are untouched and still open.
5. **Confirm the manifest is the source of truth** for tools/owner/coverage, i.e. that
   Phase B may generate the wrappers' `--allowedTools` from it rather than the reverse.
6. **Do you want a *standing* content-research workflow at all?** (Replaces the withdrawn
   decision 2.) The two campaigns end 09-03 and 09-04 having delivered ~8 runs each on two
   named topics. A permanent version is a different thing and needs its own topic rotation,
   a slot that is not 01:30 (the augustus-content collision of §6.6) and its own registry
   row. Recommended: **no** for now — let them expire, and revisit once the content
   pipeline's existing backlog is consumed.
