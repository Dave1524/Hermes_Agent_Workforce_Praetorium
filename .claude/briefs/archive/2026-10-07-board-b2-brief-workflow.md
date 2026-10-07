# Brief: B2 — board brief workflow (I2)

Spec: `.claude/briefs/agent-board-refinement-2026-09-23.md` §3.2a, §3.5, §3.6.3-§3.6.5, §3.6.8, §8 I2.
Depends on B1 (PR #92, merged, deployed). Builds only I2; the card-run page, `notion_research.py`,
the receipt `card` block and the `standing_research.env` pick are B3.

## Acceptance
1. `agent_propose.sh` exports `AGENT_RUN_ID` once, early; `propose_receipt.py` and the pick name the same id.
2. `AGENT_BOARD_PICK` in a job env makes the wrapper run `board.py pick … --run-id --workflow` after the
   `requires` pre-flight, then export `AGENT_CARD`, `AGENT_CARD_DIR`, `BOARD_ROOT`. No card: with
   `AGENT_BOARD_REQUIRED=1` a `skipped` receipt (no model); without, card-less as today.
3. `AGENT_RUN_MODE=board`: ops-style (no inbox checkout/boundary/commit); pick required; model; verify;
   outcome `BOARD` (fresh `brief.out.md` -> `board.py brief … --actor run:<id>`, receipt artifact
   `board://<card>/brief/<hash>`) else `NOPROPOSAL`.
4. Ledger-growth detector: `events.jsonl` line count before/after each attempt; growth is `VIOLATION`,
   offending lines moved to `runs/<run_id>/rejected-events.jsonl`.
5. `run_research_brief_cc.sh` (opus-5 literal, `Bash,Read,Write,Glob,Grep,WebSearch,WebFetch`, no Edit,
   guards, `vault_sync_guard.sh check`, cd to `$AGENT_CARD_DIR`), `brief_or_decline.sh` (0/3/1 contract).
6. Profile `research_brief_cc_task.md` (`Owner: claudius`), `research_brief.env.example`, units
   `research-brief.{service,timer}`, runbook row, tsv row, producers row, manifest entry with `board` key,
   three `must_not`, contract `research-brief.md`, contract env names, `board-join` coverage test,
   pinned counts +1.

## Files
bin/agent_propose.sh, bin/propose_receipt.py, bin/run_research_brief_cc.sh, bin/brief_or_decline.sh,
bin/contract_checks.py (+ design/contract-schema.md), profiles/research_brief*, systemd/research-brief.*,
config/fleet-units.tsv, bin/buzz_producers.tsv, docs/runbook.md, design/agents/claudius.toml,
design/agent-model.md, design/contracts/research-brief.md, tests/*.

## Test plan
tests/test_research_brief_smoke.sh (new), test_agent_propose_smoke.sh (board mode, ledger growth, run id),
test_propose_receipt.py (BOARD), test_fleet_ownership.sh, test_workflow_coverage.py (board-join),
test_receipt_coverage.py, test_control_room_views.py, test_contract_*; gate `bin/verify.sh`.
