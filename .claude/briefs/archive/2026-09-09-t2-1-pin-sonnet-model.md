# Brief: T2.1 — pin five sonnet workflows to claude-sonnet-5
**Date:** 2026-09-09   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 1. Red lines (`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal T1.1's ten `contract-exists` paths, nothing else. `bin/deploy` after the runner edits (drift inverts until then).

Task bullet, `docs/dev-plan-2026-09.md:86`: *"Pin `claude-sonnet-5` in the four runners (`run_daily_rhythm_cc`, `run_overnight_morning_report_cc`, `run_weekly_pre_assembly_cc`, `run_m1_signal_scan_cc`) and the five manifest rows. Drop `${VAR:-sonnet}` or default it to the full id. Smoke suites assert the full id. Gate: T1.2 green on model."* Size S, T1.2 unblocks it.

## Why

Five workflows declare `claude-sonnet` and exec `sonnet` (literal, or `${VAR:-sonnet}`). An alias silently rolls forward on the next model release — the same reason the opus runners pin `claude-opus-5`. T1.2 made that mismatch a gate (`model-alias`). This task is the pin that turns those five green. `AGENT_PROFILE=claude-sonnet` is a different fact (the runtime label agent_propose.sh records) and is not this pin.

## What to pin

| Workflow | Manifest | Runner | Today |
| --- | --- | --- | --- |
| praetorium-daily-plan | marcus.toml | `run_daily_rhythm_cc.sh` (`${DAILY_RHYTHM_MODEL:-sonnet}`) | alias |
| praetorium-eod-summary | marcus.toml | same runner | alias |
| overnight-morning-report | marcus.toml | `run_overnight_morning_report_cc.sh` (`${MORNING_REPORT_MODEL:-sonnet}`) | alias |
| weekly-pre-assembly | marcus.toml | `run_weekly_pre_assembly_cc.sh` (`${WEEKLY_PRE_ASSEMBLY_MODEL:-sonnet}`) | alias |
| m1-signal-scan | claudius.toml | `run_m1_signal_scan_cc.sh` (`--model sonnet`) | alias |

Default the three `${VAR:-…}` forms to `claude-sonnet-5` (keep the override — overnight's suite proves it). Pin m1 as a literal `--model claude-sonnet-5`, matching the opus runners. Five `model =` rows become `"claude-sonnet-5"`.

## Acceptance criteria

1. Four runners pass `--model claude-sonnet-5` as the resolved default. No remaining `${VAR:-sonnet}` or bare `sonnet` on those `--model` lines.
2. Five manifest rows declare `model = "claude-sonnet-5"`.
3. Smoke suites for those workflows assert the full id on the mock argv (`grep -qx 'claude-sonnet-5'`), not `sonnet`. `AGENT_PROFILE=claude-sonnet` stays — it is not `--model`.
4. `python3 tests/test_workflow_coverage.py`: `grep -c '^PROBLEM	model-alias	'` = 0. `bash bin/verify.sh` exit 1; red lines = T1.1's ten `contract-exists` paths only.

## Runtime actions

```
bin/deploy
```

No unit install, no restart, no live run. Next timer fire execs the deployed runner.

## Out of scope / do not touch

- T2.2, T2.3, T3.2, writing contracts, moving off `bypassPermissions`.
- `AGENT_PROFILE`, Hermes profiles, `ship-dev-plan.js`, `bin/verify.sh`, `bin/check_deploy_drift.sh`.
- `.claude/briefs/current.md` and `.claude/briefs/archive/`.
- No `sudo`, no systemd action, no `bin/deploy --prune`.
