# Brief: T2.2 — make `--allowedTools` real
**Date:** 2026-09-09   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 1. Red lines (`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal T1.1's ten `contract-exists` paths, plus any drift this task's own `bin/deploy` clears. Both fleet gates too if a unit file changes (it does not).

Task bullet, `docs/dev-plan-2026-09.md:90`: *"Make the allowlist real. Move the scheduled runners off `bypassPermissions`; canary on knowledge-digest with the run output read; then the other eight; re-run every smoke suite; add a gate rule that no `run_*_cc.sh` passes `bypassPermissions`; revise `agent-model.md` §6.1. The brief states what a bare `Bash` allowlist entry still permits, so the claim stays honest. Gate: nine runners converted, nine suites green, one live run per runner read."* Size L, unblocked by T1.2 and T1.3.

## Why

`--allowedTools` under `--permission-mode bypassPermissions` pre-approves, it does not restrict — measured 2026-09-01, `Edit` absent from a runner's list and used anyway. S2 containment is `--strict-mcp-config` plus the `agent_propose.sh` write boundary. T1.3 stopped the docs from crediting the allowlist. This task is the enforcement that lets the docs credit it again.

## Permission mode

Replace `--permission-mode bypassPermissions` with `--permission-mode dontAsk` on every `bin/run_*_cc.sh` that invokes `claude` itself. `dontAsk` auto-denies anything that would prompt; `--allowedTools` auto-allows the listed tools. Unattended jobs cannot hang on a dialog. All three bypass spellings stay forbidden (`bypassPermissions`, `=bypassPermissions`, `--dangerously-skip-permissions`).

Nine invokers, four one-line delegators (daily-plan, eod-summary, content-strategy, faceless-content) inherit. `run_standing_research_topic_cc.sh` is W19 residue with no unit (T6.3 prune); it still converts so the gate is not vacuously green against a leftover bypass, and it has no live run.

## What a bare `Bash` entry still permits

`--allowedTools` restricts which Claude Code *tools* exist in the session. It does not sandbox Bash. A runner that lists `Bash` still permits any command the model writes: `curl` to the open web, reading deny-listed paths (S2 is not Codex bwrap), writing outside the worktree. Proposal-mode `agent_propose.sh` still discards writes outside `_inbox/agents/**`. Ops-mode has no write boundary. A capability you do not want used as a Claude Code tool must be absent from the list; a capability you do not want used *via Bash* must be absent as a binary or caught by the write boundary.

## Acceptance criteria

1. No uncommented line in any `bin/run_*_cc.sh` passes bypass in any of its three spellings. `tests/test_s2_containment_claim.sh` asserts this on the live tree.
2. Those nine invokers pass `--permission-mode dontAsk` and keep `--strict-mcp-config` + empty `mcpServers`.
3. `design/agent-model.md` S2 row credits `--allowedTools` as enforced under `dontAsk`, still names `--strict-mcp-config`, and does not say the allowlist is `inert`. §2 permission-posture, §5 rule 3, and §6.1 match. The word `inert` must not remain on the S2 row — T1.3's invariant 3 is silent when the row still says inert, which is the direction it must fire if bypass returns.
4. Nine smoke suites green: daily-plan, eod-summary, overnight-morning-report, weekly-pre-assembly, raw-ingest, knowledge-digest, standing-research, m1-signal-scan, bd-followup-drafts.
5. Canary: one live `knowledge-digest.service` run, output read, did not hang on a permission prompt. Then one live run of each remaining runner that still has a unit (eight; topic-research has none).

## Runtime actions

```
bin/deploy
sudo systemctl start knowledge-digest.service    # canary; read journal
# then the other units that still exist, one at a time, output read
```

Do not enable `bd-stall-radar.timer` or `bd-followup-drafts.timer`. Do not `bin/deploy --prune`.

## Out of scope / do not touch

- T2.3's new radar runner is in-scope for the no-bypass gate (it must ship `dontAsk`) but the radar itself is T2.3.
- T2.4, D1, T3.x, T4.x, T6.3 prune of the topic-research residue.
- `.claude/briefs/current.md` and `.claude/briefs/archive/`.
- No `bin/deploy --prune`.
