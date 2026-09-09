# Brief: T1.2 — runner join (tools / mcp / model vs flags)
**Date:** 2026-09-09   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 1. Red lines (`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal T1.1's ten `contract-exists` paths **plus** exactly these five, nothing else. No `bin/deploy`.

```
PROBLEM	model-alias	praetorium-daily-plan
PROBLEM	model-alias	praetorium-eod-summary
PROBLEM	model-alias	overnight-morning-report
PROBLEM	model-alias	weekly-pre-assembly
PROBLEM	model-alias	m1-signal-scan
```

That format is already pinned by `tests/test_ship_dev_plan_workflow.sh:111` (`PROBLEM<TAB>model-alias<TAB><unit>`) and by `ALIAS_WORKFLOWS` in `.claude/workflows/ship-dev-plan.js`. Do not invent a different id or a prose detail. Do not edit either file.

Task bullet, `docs/dev-plan-2026-09.md:71`: *"Runner join: `surfaces.scheduled` tools, `tools_web`, `mcp` and each workflow's `model` against what the named runner passes (`--allowedTools`, `--strict-mcp-config`, `--model`), read out of the script. Honour claudius's per-workflow web split. Ships red on the 5 alias workflows. Gate: the red list equals those 5."* Size M, no deploy, ships red by design. Serial with T1.1 — same coverage file.

## Why

The manifests already name tools, mcp and model. The runners already pass the flags. Nothing reads one against the other, so five workflows declare `claude-sonnet` and exec `sonnet` (literal, or `${VAR:-sonnet}`) and the gate is silent. Same class as W9 / T1.1: one fact in two places, joined by convention.

T2.1 is what turns the five green (pin `claude-sonnet-5` in the four runners and the five rows). T2.2 is `--allowedTools` as enforcement (leave `bypassPermissions`). T3.2 reuses this join for `skills`. This task is the join, not those closures.

## What to join

Walk **every** parsed `[[workflows]]` entry (vacuity: same shape as T1.1). An entry with no repo `runner`, or a runner that is not a file under `ROOT`, or a runner that does not invoke `claude` with `--model` / `--allowedTools` / `--strict-mcp-config`, is counted and is not a PROBLEM. Platform scripts, `buzz-acp-launch.sh`, `agent_propose.sh`, and `bd-stall-radar` (no runner yet) are this case. Do **not** treat an empty or prose `model` (`"from the run log…"`, `"n/a — …"`) as a PROBLEM — that would fire far past five.

When the runner **is** a claude `bin/run_*_cc.sh` (or equivalent), compare, reading the script, never a deny-listed env:

1. **`--model`.** Resolve `${VAR:-default}` to the default. A comment mentioning `--model` is not the flag (`run_standing_research_cc.sh:11`). PROBLEM `model-alias` when the resolved value ≠ the workflow's `model`. Shared runner (`run_daily_rhythm_cc.sh` serves daily-plan **and** eod-summary) is two findings, not one.
2. **`--allowedTools`.** Set-equality against that owner's `[surfaces.scheduled].tools`, plus `[surfaces.scheduled].tools_web` **iff** the workflow has `web = true`. Use the `web` field, not a hardcoded unit list — standing research's unit is `agent-proposal`. Absent `web` is false. PROBLEM id `runner-tools` (green on the live tree; `check()` it).
3. **`--strict-mcp-config` / `--mcp-config`.** `mcp = []` means `--strict-mcp-config` and empty `mcpServers`. PROBLEM id `runner-mcp` (green on the live tree; `check()` it).

Print `runner join: checked N of M entries, K model-alias(es)` on every run. If `N < M`, a `runner-join-counted` PROBLEM names the undercount. `SUMMARY` gains `runner_checked=` and `model_alias=`. No `(::id)` literal in the `.py`.

Live tree today: tools and mcp match on every joined runner (marcus floor on his four; claudius floor on digest/ingest/bd-followup; floor+web on standing-research and m1). Only the five aliases are red. `grep -ciE '^PROBLEM.*(model|alias|sonnet)'` on the `.py` output equals 5 — that is `gateCmd` for T1.2; the ten `contract-exists` lines must not match it.

## Acceptance criteria

1. `tests/test_workflow_coverage.py` implements the join above. Five `model-alias` PROBLEM lines, detail exactly the unit, no extras. Checked-count line contains `33`.
2. `tests/test_workflow_coverage.sh` passes `^PROBLEM	model-alias	` through to stdout (keep the T1.1 `contract-exists` pass-through) and sets `fail=1` when any such line exists — no collapsed `FAIL:`. Vacuity is a green assert: printed checked count equals `SUMMARY entries=` and the live `[[workflows]]` count (`(::runner-join-counted)`). `(::model-alias)` is anchored on the pass-through. `runner-tools` and `runner-mcp` go through `check()` (green). The suite does not pin `= 5`.
3. `design/fleet-suites.toml` adds `model-alias`, `runner-tools`, `runner-mcp`, `runner-join-counted` to this suite's `asserts`.
4. `bash bin/verify.sh` exit 1; red lines = T1.1's ten + the five `model-alias` lines above. Commit body lists the five new lines verbatim (precedent `20f8ca2` / `9f7e977`).

## Out of scope / do not touch

- T2.1, T2.2, T3.2, T4.5, writing contracts, pinning model ids, moving off `bypassPermissions`.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, `.claude/workflows/ship-dev-plan.js`, `tests/test_ship_dev_plan_workflow.sh`.
- `.claude/briefs/current.md` and `.claude/briefs/archive/`.
- No `bin/deploy`, no `sudo`, no systemd action.
