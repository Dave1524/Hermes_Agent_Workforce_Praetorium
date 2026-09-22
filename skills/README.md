# skills/ — the pointer-skill tree

Each `SKILL.md` here is a **pointer**: a few lines naming the canonical vault directory, never
a copy of it. The vault owns the text (`08_skills/<name>/SKILL.md`) and changes it without this
repo being told, so a copy here would be a second source of truth that goes stale in silence.

**The frontmatter `description` is the one thing mirrored, verbatim.** It is the only text a
model sees before deciding to load a skill (the "level 1" of Anthropic's agent-skills note:
name + description in the system prompt, the body on demand), and it lives in *our* file.
Until 2026-09-18 every pointer paraphrased it — several dropped the vault's multi-line "Use
when …" triggers — which is a credible cause of T3.3's zero invocations across 30 runs.
`bin/pointer_skills_sync.py render` rewrites each pointer as `name` + the canonical
description block (folded YAML and quoting kept) over a fixed body naming the directory, and
`tests/test_pointer_skills.sh::pointer-description-synced` (box-gated: it reads the vault)
fails when the vault's description has moved on. `pointer-not-copy` bounds the *body*, so a
long folded description is never mistaken for a copy. **Edit the vault, then re-render** —
never the pointer.

## What this tree is for

It answers "which skills does this agent have for this workflow" — a question the box could
not answer before, because the only skill surface a headless run saw was `~/.claude/skills/`:
user-scope, uncommitted, and identical for every agent.

One plugin per owner, because a single flat tree offered to everyone is that same directory
moved into the repo. The layout is the one `--plugin-dir` actually reads:

```
skills/<owner>/.claude-plugin/plugin.json      # name = "praetorium-<owner>"
skills/<owner>/skills/<skill-name>/SKILL.md    # the pointer
```

**The `skills/` level inside an owner tree is load-bearing.** A skill directory placed at the
plugin root is not discovered — no warning, no error, it is simply not there (measured on
claude 2.1.267, 2026-09-10). `tests/test_pointer_skills.sh::skills-nested-under-skills` asserts
the layout rather than trusting it.

## How it reaches the runtime

`bin/deploy` ships `skills/` into `~/agent-workforce/`, and `bin/check_deploy_drift.sh`
compares it as a content tree in both membership directions, so the deployed copy cannot drift
from source without the gate going red. The nine scheduled runners then load their owner's
tree **by explicit path** in that deployed tree — never `~/.claude/skills/` — and each one
proves the plugin manifest is readable before it execs, because a `--plugin-dir` path that
does not exist is silent: exit 0, no diagnostic, no skills.

**Since 2026-09-18 the Buzz fleet (S1) loads the same tree.** The four Claude agents'
`claude` child runs through `buzz-team/claude-agent-wrapper.sh`, which appends `--plugin-dir
~/agent-workforce/skills/$BUZZ_AGENT_NAME` (the unit sets `BUZZ_AGENT_NAME=%i`) behind the
same readability guard — together with `--strict-mcp-config --setting-sources=` and the
rendered per-agent settings file, so nothing of Dave's user scope (his `~/.claude/skills/`,
his marketplace plugin, his MCP servers) reaches an agent session any more. Augustus, on
codex-acp, reaches his tree through `~/.config/codex-agents/augustus/skills/praetorium`, a
symlink into the deployed tree that codex follows (skills render as
`praetorium-augustus:<name>`); the link is hand-installed like a unit and asserted live by
`verify-fleet.sh` gate 15. Aurelian has a plugin manifest and no pointers, by allocation, so
the wrapper's guard is uniform across the four. `skills_mechanism = "acp-wrapper"` /
`"codex-home"` on the `buzz-agent@*` entries is what `tests/test_workflow_coverage.py` joins.

## The allocation

Frozen in `design/archive/open-decisions-closed-2026-09-07.md`. This table is joined to the
tree in both directions by `tests/test_pointer_skills.sh::allocation-matches-readme`, so it
cannot rot into prose.

| owner | pointers |
|---|---|
| augustus | `linkedin-content-engine`, `linkedin-review`, `blog-engine` |
| claudius | `prospect-research`, `meeting-prep`, `investment-research` |
| trajan | `systematic-debugging`, `test-driven-development`, `verification-before-completion`, `spec-to-code-enforcement` |
| marcus | `weekly-review`, `agent-inbox-sync`, `post-call-capture` |
| aurelian | none |

Which of these a run actually opens is measured since T3.3 (2026-09-11): the weekly digest at
`_inbox/agents/_metrics/scorecard.md` carries a `## Pointer skills (T3.3)` table of runs that read
each pointer versus runs offered it, rolled up from the `skills=` / `skills_offered=` keys
`agent_propose.sh` records per run (`docs/runbook.md` § Agent-run metrics & scorecard).

Thirteen pointers. The frozen decision's prose says "1 of these 14 is named by a live
workflow"; its own table sums to 13, and 13 is what exists here — the 14 is an arithmetic slip
carried into `docs/dev-plan-2026-09.md`, corrected there and left standing in the archive,
which is a record of what was written rather than a live document.

**A pointer must not duplicate a task profile that already owns the same surface.** That is
why `morning-startup` and `eod-wrap` are absent: `profiles/daily_plan_task.md` and
`profiles/eod_summary_task.md` already own Dave's day on the scheduled surface, and a pointer
beside them would be a second owner of one job. Asserted as
`tests/test_pointer_skills.sh::no-profile-duplicate`.

## Two things worth knowing before reading a green run as more than it is

**`agent-inbox-sync` is a name collision, not a duplicate.** The pointer names the vault skill;
trajan's `agent-inbox-sync` is a `surface = "platform"` systemd timer that runs a script and
no model. Different things, same name.

**Every pointer now reaches its owner on at least one surface, and the manifests say which.**
Since T3.2 (2026-09-11) every `[[workflows]]` entry in `design/agents/*.toml` carries
`skills = [...]`, and `tests/test_workflow_coverage.py` joins each list to the offer its
mechanism really delivers: claudius's and marcus's scheduled entries declare their three
pointers (the runner's `--plugin-dir` tree); augustus's two content triggers declare
`["linkedin-content-engine"]` under `skills_mechanism = "heading-extraction"` (the only
pointer their profile extracts through `bin/skill_sections.sh`); trajan's sixteen platform
entries (no model to offer a skill to) declare `[]`. Until 2026-09-18 the five `buzz-agent@*`
entries declared `[]` too — codex-acp and claude-agent-acp took no `--plugin-dir` — and 6 of
the 13 pointers (trajan's four, `linkedin-review`, `blog-engine`) were offered to nobody.
Now each `buzz-agent@<owner>` entry declares its owner's pointers under `acp-wrapper` /
`codex-home`, so trajan's four reach him and augustus's three reach him on S1; aurelian's
stays `[]` by allocation. Do not close a remaining scheduled-surface gap by inventing a
runner. Offered is not used: which pointers a run opens is T3.3's question on S2 and the
`skills` block of each interaction receipt on S1 (`bin/scorecard.sh` folds both).

**The gate cannot list what a live session loaded.** `claude plugin details` does not accept
`--plugin-dir`, so there is no deterministic CLI way to enumerate a session-loaded plugin's
skills, and no suite in this repo spends model tokens. What is asserted instead is the chain
every link of which is checkable: the tree is well-formed, each runner names its owner's tree
by explicit path, the guard makes a missing tree fatal, and drift keeps deployed equal to
source.

## Behavioural evals (T8.4)

Everything above this section is asserted **deterministically**, and the header of
`tests/test_pointer_skills.sh` is explicit that this is a chain and not a verdict: the tree is
well-formed, each runner names its owner's tree by explicit path, the guard makes a missing tree
fatal, drift keeps deployed equal to source. Each link is checkable. What the chain exists to
produce — the model actually firing the skill — was asserted nowhere, which is how T3.3's zero
sat unexplained for three days after its cause had already been fixed.

`bin/agent_config_eval.sh` is the missing half, and the only thing on this box that spends model
tokens to answer a question about itself.

```
bin/agent_config_eval.sh                       # score every owner's cases against the baseline
bin/agent_config_eval.sh --owner claudius      # one owner
bin/agent_config_eval.sh --self-check          # …and prove the suite can still go red
bin/agent_config_eval.sh --changed-since origin/main   # the verify gate's own entry point
bin/agent_config_eval.sh --record              # re-record the baseline. A deliberate commit.
```

**Adding a case.** Create `skills/<owner>/evals/<pointer>-<what>/case.yaml` — beside `skills/`,
never inside it, and never at `skills/evals/`, which `owner_dirs` would read as a sixth owner.
Name it after the pointer it is about; `tests/test_agent_config_eval.sh::eval-case-names-skill`
joins the two. Then `--record` and commit the baseline in the same change: a case with no
recorded score is a pass mark nobody measured, and the gate calls it `UNBASELINED` and goes red.

**The verdict is regression, not an absolute mark** — `bin/fleet_eval.sh:13-20`'s reasoning
applies unchanged. An improvement is reported and the baseline is left alone; re-recording it is
a commit that says why, never something the weekly run does to its own pass mark.

### What a green run does and does not say — MEASURED 2026-09-22, claude 2.1.278, claude-opus-5

The brief for this work assumed the T3.3 incident would make the negative control: restore
claudius's pre-`400e7ef` `meeting-prep` description — `Prepare for a meeting from what the vault
already knows.`, with the vault's `Use when Dave says 'prep for meeting with [company/person]'`
triggers dropped — and watch the case go red. **It does not.** The paraphrased description scored
**1.000 over three runs**, and a second prompt written to avoid the word "meeting" entirely ("I've
got a call with Kestrel Cold Logistics on Thursday. Get me ready for it.") scored **1.000 over two
runs against both descriptions**.

The reading: for a skill whose **name** already matches the request, the description is not what
decides. `meeting-prep` is named for what the user is asking for, so the trigger text is
redundant; the pointers where a description carries real load are the ones whose names do *not*
match how Dave would phrase the request. That does not make the 2026-09-18 re-render wrong — the
description is still the only text a model sees before loading a skill, and mirroring the vault's
is still right — but it does mean **a paraphrased description is not a demonstrated cause of
T3.3's zero**, and this section supersedes the sentence above that calls it a credible one.
The likelier cause is the other half the brief already named and put out of scope: the scheduled
job prompts do not use the trigger phrasing at all.

So the negative control is a different mutation, and a better one: every skill directory moved
from `<plugin>/skills/<name>/` to `<plugin>/<name>/`. That is the trap
`tests/test_pointer_skills.sh:17-19` measured on claude 2.1.267 — a skill directory at a plugin
root is not discovered, with no warning and no error — and it scores **0.000**. Every file is
still present and readable; the loader simply does not see them, which is exactly the class of
failure that is silent on this box today.

### Cost

Measured on the first case: `max_turns: 2`, `allowed_tools: [Skill]`, the Skill call on turn 1,
**~4s and ~$0.081 a run** on `claude-opus-5`, so ~$0.24 a case at `runs: 3`. The eval child's cwd
is deliberately outside `$HOME` — under it, `~/CLAUDE.md` (46 KB) and the shared memory pool load
into *every* run, which both inflates that figure and means the eval measures Dave's machine
instructions instead of the pointer descriptions under test. The runner refuses a `TMPDIR` inside
`$HOME` rather than warning about it, because the wrong measurement still produces a number.
