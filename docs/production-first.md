# Production first

The rule below is the single source. `bin/production_first_sync.py` copies the marked block into
the instruction files every agent session loads and `check` fails when a copy has drifted:

| Where | File | Read by |
|---|---|---|
| Box | `~/.claude/CLAUDE.md` | Claude Code, every project |
| Box | `~/.codex/AGENTS.md` | Codex, every project (`~/AGENTS.md` is a symlink to it) |
| Mac | `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md` | the same two, on the Mac |
| Both | `~/.claude/commands/plan-feature.md`, `ship.md` | the plan and ship loops; they carry the brief sections the rule asks for |

Change the rule here, then `python3 bin/production_first_sync.py apply`. Never edit a copy.

<!-- production-first:start -->
## Production first

Applies to every plan, design and recommendation, in any project.

- **Never choose, rank or recommend a direction because it is cheaper, quicker or smaller.**
  Tokens, build time and diff size are not criteria; there is budget for the right design.
  "Pilot", "MVP" and "for now" are not reasons.
- **Research before designing.** Work out how production systems solve this class of problem,
  and ground it: context7 for the libraries involved, web search for architecture write-ups,
  standards and post-mortems, the codebase for what already exists. Record it in the brief under
  `## Design research`: at least two established patterns, the sources, and why one fits.
- **For every state change or trigger the feature touches, write down:** the trigger, the
  latency it must meet, what happens when the trigger fails, idempotency, how it is observed,
  and what grows (load, cost, data). Choose the mechanism last.
- **Dave decides direction; you prepare the decision.** Every real fork goes under
  `## Decisions for Dave`: the options, what each costs later (rework, operations, risk), what
  the research supports, the complete option first. Do not pick for him, do not bury a fork in
  prose, and stop at the gate before building while one is open.
- **A smaller first step is an increment on the same architecture**, never a different one that
  will be replaced. If a design note holds an earlier "pilot" decision, reopen it and say so.
<!-- production-first:end -->
