# Brief: T1.1 — contract-path join in the coverage checker
**Date:** 2026-09-09   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 1, red lines (`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal exactly the ten missing contract paths. No `bin/deploy`.

Task bullet, `docs/dev-plan-2026-09.md:67`: *"Contract-path join in `tests/test_workflow_coverage.py`: every `contract` value resolves to a file. The rule reports how many entries it checked and fails if that is below the manifest's entry count. Ships red on the 10 missing files. Gate: the red list equals the 10 in the baseline."* Size S, no deploy, ships red by design.

## Why

T1.4 grades the two contracts that exist and deliberately does not report a manifest naming a file that is not there. Ten `contract = "design/contracts/<stem>.md"` lines point at nothing. Until this join, that is convention only — the same class as W9. T4.1–T4.3 close the ten by writing the files; this rule is what those tasks turn from red to green. T4.5 later flips the rule from "resolves if present" to "present and resolves"; this task does not.

## Acceptance criteria

1. `tests/test_workflow_coverage.py` walks every parsed `[[workflows]]` entry. An empty or absent `contract` is counted and is not a `PROBLEM`. A non-empty value that is not a file under `ROOT` is one `PROBLEM` per distinct path, assertion id `contract-exists`, detail exactly the declared path. Two entries sharing `augustus-content.md` produce one line, not two. Prints `contract join: checked N of M entries, K missing file(s)` on every run. If `N < M`, a `contract-join-counted` PROBLEM names the undercount. `SUMMARY` gains `contract_checked=` and `contract_missing=`. No `(::id)` literal in the `.py`.
2. `tests/test_workflow_coverage.sh` passes `^PROBLEM	contract-exists	` through to stdout (other PROBLEM ids stay filtered) and sets `fail=1` when any such line exists — no collapsed `FAIL:` line, because the land set-diff wants ten `PROBLEM` lines. Vacuity is a green assert: the printed checked count equals `SUMMARY entries=` and the live `[[workflows]]` count computed in bash (`(::contract-join-counted)`). `(::contract-exists)` is anchored on the pass-through. The suite does not pin `= 10`.
3. `design/fleet-suites.toml` adds `contract-exists` and `contract-join-counted` to this suite's `asserts`.
4. Live tree: `python3 tests/test_workflow_coverage.py` prints a checked-count line containing `33`, and `grep -c '^PROBLEM.*design/contracts/'` = 10. The ten stems are `augustus-content`, `bd-followup-drafts`, `bd-stall-radar`, `m1-signal-scan`, `overnight-morning-report`, `praetorium-daily-plan`, `praetorium-eod-summary`, `raw-ingest`, `standing-research`, `weekly-pre-assembly`. `knowledge-digest` and `buzz-interactive` are not among them.

## Out of scope / do not touch

- T1.2, T4.5, writing any of the ten files.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, `.claude/workflows/ship-dev-plan.js`.
- `.claude/briefs/current.md` and `.claude/briefs/archive/`.
- No `bin/deploy`, no `sudo`, no systemd action.
