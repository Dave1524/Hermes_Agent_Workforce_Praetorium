# SDLC measurements — ship-dev-plan LAND records

MEASURED 2026-09-23

```
python3 bin/sdlc_measurements.py --repo . --since 2026-09-01 --runs '/home/dave/.claude/projects/-home-dave-dev-agent-workforce/*/workflows/wf_*.json' --markdown --today 2026-09-23
```

| task | archive | record | first_pass | rework | harness | landed_by | named∩touched | unplanned | not_done | fidelity | range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T6.2 | e43b85d | verifyExit 0 | no | 1 | 1 | hand | 11 | 0 | 0 | 1.00 | d3c3545^..e43b85d^ |
| T1.4 | 9df0f25 | verifyExit 0 | yes | 0 | 0 | workflow | 5 | 0 | 0 | 1.00 | 7551e1c^..9df0f25^ |
| T1.3 | 0745241 | verifyExit 0 | no | 1 | 0 | workflow | 2 | 0 | 0 | 1.00 | bc91e04^..0745241^ |
| T6.4 | 9e028e6 | verifyExit 0 | no | 3 | 1 | workflow | 2 | 0 | 0 | 1.00 | 5c93ea6^..9e028e6^ |

## Plan fidelity — the sets

- none: every recorded range touched exactly the files its brief named

## How to read it

- `first_pass`, `rework`, `harness` come from the run records (one `land:<id>` attempt each);
  a `(git)` cell is the proxy: commits between the brief's first commit and its archive.
  `harness` is an attempt the harness lost (null return, errored agent, a land that did not
  land), never counted as rework.
- `fidelity` is file-set overlap, |named ∩ touched| / |named ∪ touched|. It saturates: a
  deviation lands as `fix(` commits inside files the brief already named, so it shows in
  `rework`, not here. That is the finding, not a defect of the number.
- `range: undefined` means the brief was added more than once or in a batch commit with
  other briefs, so no range belongs to it alone.

## No LAND record

- T8.4 — `77d5baa` chore(briefs): archive the T8.4 behavioural-evals brief
- T8.2 — `8555d51` chore(briefs): archive T8.2, drop the T8.5 plan copy (landed as #63, #65)
- T8.3 — `de22eee` docs(briefs): archive the T8.3 version-review-rubric brief
- T8.1 — `5de7bcb` chore(briefs): archive the T8.1 ship-rails-hook brief
- T5.3g — `7f942cc` docs(briefs): archive T5.3g — runtime controls: start / stop / restart an agent from the Agents view
- T5.3f — `7166798` docs(briefs): archive T5.3f — workflow roles, the Agents view, requires and guards
- T5.3c — `e8028ca` docs(briefs): archive T5.3c — route actionable workflow incidents to Buzz
- T5.2 — `b9f68a4` docs(briefs): archive T5.2 — executor wiring
- T5.3b — `7b90c95` docs(briefs): archive T5.3b — schedule-retirement-prs
- T5.3a — `3c038dc` docs(briefs): archive T5.3a — live-workflow-controls
- T5.3 — `4421dce` docs(briefs): archive T5.3 — control-room-screen
- T3.1 — `a83792a` feat(skills): T3.1 — pointer-skill tree, deployed and drift-checked
- buzz-task-scheduling — `8440e7d` Auto-sync: main updates at 2026-09-10 10:46:28 UTC
- T4.0 — `19d7295` feat(contracts): T4.0 — executable acceptance checks, and convert knowledge-digest
- T7.1 — `4f51ba9` fix(agent-propose): T7.1 — scope the decline sentinel to this run of this job
- T1.1 — `123ce4e` docs(dev-plan): re-order after the 09-09 batch, and record two live defects
- T1.2 — `123ce4e` docs(dev-plan): re-order after the 09-09 batch, and record two live defects
- T2.1 — `123ce4e` docs(dev-plan): re-order after the 09-09 batch, and record two live defects
- T2.2 — `123ce4e` docs(dev-plan): re-order after the 09-09 batch, and record two live defects
- T2.3 — `123ce4e` docs(dev-plan): re-order after the 09-09 batch, and record two live defects
- T2.4 — `123ce4e` docs(dev-plan): re-order after the 09-09 batch, and record two live defects
- workflow-ship-feasibility — `2e7d0f9` docs(briefs): archive workflow-ship-feasibility — implemented as the ship-dev-plan workflow
- augustus-content-automation-diagnosis — `6dd2920` docs(briefs): prune eight duplicated briefs, archive two finished ones
- fleet-guard-suite-connector-deny — `6dd2920` docs(briefs): prune eight duplicated briefs, archive two finished ones
- hermes-kanban-retirement — `79c8e67` docs(briefs): archive the hermes kanban retirement brief
- skills-heading-extraction — `ac11293` docs(briefs): archive brief 4 — skills-heading-extraction (D3 part 1)
- deploy-drift-check — `8bb6b39` docs(briefs): archive brief 2 — deploy-drift-check (D8)
- workflow-coverage-checker — `a2f4841` docs(briefs): archive brief 3 — workflow-coverage checker

## Not derivable without new instrumentation

- Who approved: no reviewer identity is recorded anywhere in a LAND record.
- Review effort actually used and time-in-review: only the requested effort
  (`TASKS[id].review`) exists.
