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

**This file may hold exactly one markdown table.** `readme_pairs`
(`tests/test_pointer_skills.sh:147`) reads every `|`-leading line in this README as an
allocation row, so a second table anywhere below is parsed as more pointers and the join goes
red naming rows that were never meant to be pointers. Measured 2026-09-22, by writing one.
It fails closed, which is the cheap direction — but write tabular data further down as a
fenced block, the way the eval measurements below are.

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
went three days without anyone being able to say whether it was still true, let alone why.

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

**Two kinds of case, and the suffix is what tells them apart.** A `<pointer>-fires` case asks
whether the skill still fires for the phrase its description says triggers it. A
`<pointer>-must-not-fire` case asks the opposite — that it stays out of an adjacent ask — and
`bin/agent_config_eval_compare.py` flips the verdict for it: baselined at 0.000, a **rise** is
red (`OVERFIRED`) and a fall is reported. The direction rides on the case name and not on a
field in the baseline, because `--record` rewrites that file wholesale from the measured scores:
a field would be dropped on the first re-record and the case would silently become a floor
again. Write the off-trigger prompt *adjacent* to the skill's subject — a control the model gets
right on topic alone measures nothing.

**Coverage is joined in both directions.** Every pointer has a `-fires` case and every owner
offering pointers has at least one ceiling case
(`tests/test_agent_config_eval.sh::every-pointer-has-eval`); every case names a pointer its owner
really has (`::eval-case-names-skill`). A pointer with no case is a skill this suite would never
notice going quiet, which is the T3.3 blind spot one pointer at a time.

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

### What the eval sandbox is — MEASURED 2026-09-23, claude 2.1.278

A case's prompt is not run against this repo, this box, or anything the skill's description
describes. It is run against an **empty directory**: `<temp>/home/cwd`, an initialised git repo
with no files in it. Three consequences, each of which cost a wrong diagnosis before it was
measured:

**`allowed_tools:` adds, it does not restrict.** Every case here declares `allowed_tools:
[Skill]`, which reads as a Skill-only session and is not one — the eval child comes up with
`Task`, `Glob`, `Grep`, `Read`, `Skill`, `TaskStop` and `ToolSearch` whatever the list says. The
list is consulted only for the **gated** tools (`Write`, `Edit`, `Bash`, `WebFetch`, `mcp__*`),
and naming one there is only half the grant: `bin/agent_config_eval.sh` must pass
`--allow-tools <tool>` as well. Either half alone leaves the session without it, silently.

**A prompt may not refer to anything it does not carry.** "Implement a retry wrapper around the
HTTP client" names an artefact the sandbox does not contain, so the model opens by looking for
it — `Glob`, no hits, budget spent. It is measuring orientation, not the trigger. A case for a
skill whose moment is *before writing code* has to supply both halves of that moment: the code,
inline in the prompt, and a tool that can write.

**`--keep-temp` is the only way to read a miss.** Without it the tool unlinks its temp root on
exit, `tracePath` in the result JSON points at nothing, and a 0.000 is an unexplained number.
`trajan/test-driven-development-fires` sat at 0.000 for nine runs of nine and was written up as a
vault-description defect on exactly that evidence; one trace read with the flag falsified it.
Read the trace before writing down a cause.

**`scaffold_script` does not execute here.** The bundle's schema accepts the key — under
`execution:`, at top level, as `scaffold:` or `script:` — and nothing runs: no marker file, no
diagnostic, not even on a body whose only statement is `exit 3`. It would be the right fix for
the empty directory (seed the repo, leave the prompt alone); until it works, the artefact goes in
the prompt. Recorded as measured, not worked around quietly.

### What the first full measurement found — MEASURED 2026-09-22, claude-opus-5, runs 3

**Three** full runs of the unchanged tree, 17 cases each. Per case, per run:

```
                                          run A   run B   run C
the 9 other -fires cases                  1.000   1.000   1.000
the 4 -must-not-fire cases                0.000   0.000   0.000
claudius/investment-research-fires        0.333   0.000   0.333
trajan/spec-to-code-enforcement-fires     0.333   0.333   0.000
trajan/systematic-debugging-fires         1.000   1.000   0.333
trajan/test-driven-development-fires      0.000   0.000   0.000
```

Three things follow, and all three are now in the design rather than in a paragraph.

**Nine of thirteen pointers fire every single run, and every ceiling holds.** That is the part
that gates, and it is the majority of the tree.

**Two of the four moving cases were broken cases, not findings — corrected 2026-09-23.**
`trajan/test-driven-development-fires` read 0.000 nine runs of nine, and this section said the
fix was the vault's `08_skills/` text. **That was wrong**, and it was wrong in the way this file
is least able to catch: a confident cause written from a score, with the trace already deleted.
Both trajan cases asked for work on an artefact the empty sandbox does not contain — "the HTTP
client", a spec and a module — and both spent their budget looking for it. They now carry the
artefact in the prompt, the runner grants `--allow-tools Write`, and they read **0.400** (twice,
five runs each) and **1.000** (5 of 5). See § What the eval sandbox is, and the baseline's notes
on both cases for what the remaining 0.400 measures.

What survives of the original reading: the 0.000 was real, it was reproducible, and no amount of
re-running it would have explained it. What does not: the cause. **A cause is not measured until
the trace is read** — one `--keep-temp` run, about $0.30, against the several paid runs and one
planned vault change the wrong cause bought.

**Three cases swing by a whole tolerance step between identical runs.** Run C called
`systematic-debugging` a `REGRESSION` against a baseline of 1.000, correctly by the rule and
wrongly about the world: nothing had changed. A gate that goes red for reasons nobody chose is
muted within a week — the same argument `bin/fleet_eval.sh:13-20` makes, arriving from the other
direction. So the baseline entry for each of those four carries **`gate: false` and a `notes`**:
still measured, still printed with its score and its movement, still in the scorecard, and
unable to fail the run. 13 of 17 cases carry a verdict.
`tests/test_agent_config_eval.sh::baselined-case-can-go-red` will not let that be quiet — a case
that cannot carry a verdict (one recorded inside the tolerance of its floor or ceiling, where
there is nothing left to fall to) is legal only while it declares `gate: false` **with** a
`notes`, and every `gate: false` must carry one. `--record` carries both forward rather than
remeasuring them away.

**Raising `runs` is the other answer, and it is Dave's call, not the suite's.** At `runs: 9`
those three would likely stabilise and everything would gate — at about four times the cost per
run. Deleting a `gate: false` line is how that decision gets made.

**The tolerance is per case, because `runs` is.** A case sets its own `runs`, and 1/runs is the
size of one flaky run *of that case*. The moment the tree went mixed — the two repaired trajan
cases at 5, everything else at 3 — a single global figure was wrong from whichever end it came:
1/5 makes one flaky run of a runs=3 case a REGRESSION, and 1/3 absorbs a real 0.2 drop on a
runs=5 one. `--record` writes each case's `runs` beside its score and the comparator derives the
tolerance from it; the file-level `tolerance` remains only as the fallback for an entry recorded
before this, and is the coarsest of them so an unlabelled case is never falsely red.

### Cost

Measured on the first case: `max_turns: 2`, `allowed_tools: [Skill]`, the Skill call on turn 1,
**~4s and ~$0.081 a run** on `claude-opus-5`, so ~$0.24 a case at `runs: 3` and **~$4 for a full
17-case record** at `-j 4`. The weekly timer adds one more case for the negative control, not one
more owner: `--self-check` runs a single `-fires` case broken, against a baseline filtered to that
case — against the whole file the owner's other cases come back `MISSING` and the control would
go red for a reason that is not the one it exists to prove. The eval child's cwd
is deliberately outside `$HOME` — under it, `~/CLAUDE.md` (46 KB) and the shared memory pool load
into *every* run, which both inflates that figure and means the eval measures Dave's machine
instructions instead of the pointer descriptions under test. The runner refuses a `TMPDIR` inside
`$HOME` rather than warning about it, because the wrong measurement still produces a number.
