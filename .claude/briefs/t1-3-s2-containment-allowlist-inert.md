# Brief: T1.3 — S2 containment is `--strict-mcp-config` + the write boundary; `--allowedTools` is inert
**Date:** 2026-09-08   **Verify:** `bash bin/verify.sh` (redirect to a file; it is ~200 KB) — exit 0, red lines equal the baseline exactly (baseline on `main`: none)

Task bullet, `docs/dev-plan-2026-09.md:75`: *"Correct `design/agent-model.md:60` and §6.1. Today S2
containment is `--strict-mcp-config` plus the `agent_propose.sh` write boundary; the allowlist is
inert under `bypassPermissions`. Gate: no line credits `--allowedTools` as enforcement. T2.2 revises
this again when enforcement lands."* Size S, no deploy, ships no red.

## Why

All nine `bin/run_*_cc.sh` pass `--permission-mode bypassPermissions` **and** `--allowedTools`.
Under bypass an allowlist pre-approves; it does not restrict — measured 2026-09-01
(`design/archive/open-decisions-closed-2026-09-07.md:258`): `Edit` was absent from a runner's
list and was used anyway. `design/agent-model.md` still names "explicit `--allowedTools`" as
S2's tool set (`:60`), calls the allowlist a "real boundary" (`:138`), credits it for the
outward-connector guarantee (§6.1 `:425`) and lists "allowlist absence" as an enforcement point
(§5 rule 3 `:392`). Anyone who drops `--strict-mcp-config` believing the allowlist is the guard
removes containment with no error. What actually holds S2: **no MCP server is loaded**
(`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`, asserted per runner by every smoke
suite), so no connector tool exists in the session; and **the proposal write boundary**
(`agent_propose.sh:393-401`, `tests/test_fleet_guards.sh::propose-write-boundary`), which
discards a proposal-mode run's whole worktree unless every change is under `_inbox/agents/**`.
The boundary governs what reaches the vault, not what the process may do — `Bash` under
bypass is unbounded, which T2.2 states when it makes the allowlist real.

## Acceptance criteria

1. **No line of `design/agent-model.md` credits `--allowedTools` as enforcement.** Judged per
   hit of `grep -n -- '--allowedTools' design/agent-model.md`. Specifically:
   - `:24-27` (§1 bullets): "he has exactly `…`" → the runner *declares* that list; the
     containment is "no MCP server at all", not the list;
   - `:60` (S2 row, *Tool set* column): names `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`
     first, then the `agent_propose.sh` write boundary (proposal mode; ops mode has none), and
     says `--allowedTools` is passed but **inert** under `bypassPermissions` until T2.2;
   - `:136-139` ("Permission posture"): "an allowlist (S2)" is no longer listed as a real
     boundary; MCP-emptiness and the write boundary are;
   - `:392` (§5 rule 3): "allowlist absence" is replaced by the mechanisms that exist
     (no loaded server, write boundary, deny-list rule);
   - `:424-426` (§6.1): "those tools are not in any `--allowedTools`" → the connector tools do
     not exist in an S2 session because no MCP server is loaded; dated note that this section
     credited the wrong mechanism from 2026-09-01 to 2026-09-08.
   `:196`, `:603`, `:612`, `:680` describe generation/validation of the flag, not enforcement —
   unchanged.
2. `grep -n 'strict-mcp-config' design/agent-model.md` names it as the S2 containment on the S2
   row (the land gate's second check).
3. `tests/test_s2_containment_claim.sh` exists, runs in the `tests/*.sh` sweep, exits 0 after
   the edit, and was **red** before it (S2 row lacks `inert`). It joins the doc's S2 row to the
   runners so the claim cannot outlive its mechanism, and stays green through T2.2 without
   editing:
   - every `bin/run_*_cc.sh` carries `--strict-mcp-config` and `'{"mcpServers":{}}'` — the
     mechanism the row credits, named per runner if missing;
   - exactly one S2 row; it names `--strict-mcp-config`;
   - **while any** `bin/run_*_cc.sh` passes `--permission-mode bypassPermissions`, the S2 row
     contains the word `inert` (vacuous once T2.2 removes bypass; fires again if a runner
     regains it while the row claims a real allowlist).
   Carries the repo's `assert()` (pipefail scoped off) and the `yes | grep -q y` canary; no box
   precondition, no `SKIP:` line, no change to `tests/ci-expected-skips.txt`.
4. `bash bin/verify.sh` exits 0 with no red lines (baseline: none). `bin/deploy` is not run —
   neither file is in a deployed tree.

## Files to modify

- `design/agent-model.md` — the five sites under criterion 1, minimal wording; one dated
  correction note in §6.1, no essay. Nothing else in the file moves.

## Files to create

- `tests/test_s2_containment_claim.sh` — header states the invariant (the S2 row may not credit
  the allowlist while a runner runs under bypass; the mechanism it credits instead must be in
  every runner) and what it does NOT assert (that the allowlist is inert — that is measured, not
  testable from a checkout; that `Bash` is bounded — it is not). Checkers: `bypass_runners DIR`,
  `uncontained_runners DIR`, `s2_row_defects FILE DIR`. Groups: 0 canary; 1 fixtures in
  `$(mktemp -d)` (bypass runner + row crediting the allowlist → named; bypass runner + `inert`
  row → silent; no bypass runner + row without `inert` → silent; runner missing
  `--strict-mcp-config` → named; row missing `--strict-mcp-config` → named; two S2 rows → named);
  2 the live `design/agent-model.md` and `bin/`. `set -uo pipefail`, `exit $fail`.

## Test plan

- TDD: write the suite, run it — group 2 red on the current doc (`S2 row does not say the
  allowlist is inert while N runner(s) pass bypassPermissions`), group 1 green. Edit the doc;
  group 2 green.
- `bash tests/test_s2_containment_claim.sh` → exit 0, `FAIL:` count 0.
- `shellcheck -S error tests/test_s2_containment_claim.sh` clean.
- `grep -n -- '--allowedTools' design/agent-model.md` — read every hit; none credits enforcement.
- `bash bin/verify.sh > "$SCRATCH/verify.out" 2>&1; echo $?` → 0; `grep -cE '^ *FAIL:|PROBLEM|DRIFT '` → 0.

## Out of scope / do not touch

- `bin/run_*_cc.sh` header comments that say "explicit tool allowlist" (`run_daily_rhythm_cc.sh:4`,
  `run_weekly_pre_assembly_cc.sh:4`, `run_standing_research_topic_cc.sh:5`) — editing `bin/`
  turns the drift check red until deploy, which this task does not run; T2.2 rewrites every
  runner anyway.
- `design/agents/*.toml` — `tools` fields are declarations the T1.2 join reads; `must_not`
  `why` lines name the settings file / harness, not the allowlist. Nothing to correct.
- `design/agent-model.md:196` "11 hand-written strings" (nine runners today) — a count, not
  an enforcement claim; T1.2 owns the runner join.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, any existing test, `tests/ci-expected-skips.txt`.
- `.claude/briefs/current.md` and `.claude/briefs/archive/` — belong to a live brief (T0.3).
- No `bin/deploy`, no `sudo`, no systemd action.

## Notes / preconditions

- Confirmed: 9 runners in `bin/run_*_cc.sh`; all 9 pass `--permission-mode bypassPermissions`,
  `--strict-mcp-config`, `--mcp-config '{"mcpServers":{}}'` and `--allowedTools`.
- Confirmed: no test mentions `allowedTools`; eight smoke suites assert `--strict-mcp-config` +
  `mcpServers` in the fake-claude argv; `test_fleet_guards.sh::propose-write-boundary` asserts
  the write boundary (box-gated suite — skips off the box).
- Confirmed: ops-mode jobs (daily-plan, eod-summary, overnight-morning-report, the two spent
  campaign runners) skip the write boundary (`agent_propose.sh:382-390`); the row must say
  "proposal mode".
- `bin/verify.sh` runs each `tests/*.sh` with `bash "$t"`; exit 0 or 77 is green.
- Worktree branch `worktree-wf_7b9a2821-7b1-2`; the land step fast-forwards `main`.
