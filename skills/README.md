# skills/ — the pointer-skill tree

Each `SKILL.md` here is a **pointer**: a few lines naming the canonical vault path, never a
copy of it. The vault owns the text (`08_skills/<name>/SKILL.md`) and changes it without this
repo being told, so a copy here would be a second source of truth that goes stale in silence.

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

**Trajan's and Augustus's trees reach no scheduled runner today.** Trajan's fifteen workflows
are all `surface = "platform"` (no model to offer a skill to) and Augustus's scheduled work is
`buzz_dispatch` on codex-acp, which takes no `--plugin-dir`. Their trees exist because the
frozen allocation names them and because T3.2 joins `skills = [...]` in `design/agents/*.toml`
against them. That they are offered to nobody is recorded state, not an omission — do not
close the gap by inventing a runner.

**The gate cannot list what a live session loaded.** `claude plugin details` does not accept
`--plugin-dir`, so there is no deterministic CLI way to enumerate a session-loaded plugin's
skills, and no suite in this repo spends model tokens. What is asserted instead is the chain
every link of which is checkable: the tree is well-formed, each runner names its owner's tree
by explicit path, the guard makes a missing tree fatal, and drift keeps deployed equal to
source.
