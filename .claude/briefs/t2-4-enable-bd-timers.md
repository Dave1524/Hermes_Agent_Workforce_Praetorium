# Brief: T2.4 — enable both BD timers with canary runs
**Date:** 2026-09-09   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 1. Red lines (`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal T1.1's ten `contract-exists` paths, plus any drift this task's own `bin/deploy` clears.

Task bullet, `docs/dev-plan-2026-09.md:100`: *"Enable both BD timers. Fix the drafts example's `AGENT_PROFILE` line; diff repo and `/etc` units both ways (OnFailure parity); enable; one live run each with output read; manifests dormant → standing; §10 item 1 closed. Gate: two live runs each produced a proposal or a `DECLINE:`."* Size M, blocked by T2.3 (Done) and D1 (Dave, env files).

## Why

Both units have been installed in `/etc` and disabled since before T2.3. The radar now has a CC runner (T2.3). Dave's §10 item 1 was "enable or retire"; the plan chose enable. A status of `standing` that the timers do not match is the same class of lie the dormant-vs-planned mix-up was.

## AGENT_PROFILE — do not apply the 09-01 merge

The 2026-09-01 timers brief said change `AGENT_PROFILE=claude-opus` to `claudius`. W1 (2026-09-02) split the fields: `AGENT_PROFILE` is the runtime (`cost.log`'s `profile=`), `AGENT_OWNER` is the persona (episodic memory). T2.3's radar example and every other opus job use that split. `tests/test_bd_followup_drafts_smoke.sh` asserts `AGENT_PROFILE=claude-opus`. The drafts example already has `AGENT_OWNER=claudius`. **No line change.** D1 copies the example as-is.

## OnFailure parity — already identical

Measured 2026-09-09, `diff` repo ↔ `/etc` on all four unit files is empty. Both services already carry `OnFailure=agent-alert@%n.service`. Record that; do not "fix" a gap that is not there. Do not change OnCalendar or the design comments.

## Acceptance criteria

1. `profiles/bd_followup_drafts.env.example` still has `AGENT_PROFILE=claude-opus` and `AGENT_OWNER=claudius`.
2. Repo and `/etc` BD units remain byte-identical (re-diff both ways after any install).
3. Two live runs of `bd-stall-radar.service` and two of `bd-followup-drafts.service`, output read from the journal (never exit code alone). Each produced this run's dated proposal **or** a log-tail `DECLINE:`. A missing-env `block_exit` is a stop, not a run: print the `! install -m 600 …` lines for Dave and leave both timers disabled.
4. After those four runs: `systemctl enable --now` both timers. `systemctl is-enabled` is `enabled`. `systemctl list-timers` shows a next elapse tonight (Sun–Thu 23:00 / 23:30).
5. Manifests and `config/fleet-units.tsv`: both rows `dormant` → `standing`. Trigger lines drop "INSTALLED BUT DISABLED". Flip **after** enable, so status matches the box (agent-model.md §4 rule 2).
6. §10 item 1 on the source Notion page is closed with a dated note. Tracker T2.4 → Done.
7. `bash bin/verify.sh` exit 1; red = T1.1's ten `contract-exists` paths only.

## Runtime actions (order is load-bearing)

```
# 1. Probe D1 without reading the deny-listed tree.
sudo systemctl start bd-stall-radar.service
journalctl -u bd-stall-radar.service -o cat --since '2 min ago'
# missing-env block_exit → STOP, timers stay disabled.
# run attempt … run_bd_stall_radar_cc.sh → continue.

sudo systemctl start bd-followup-drafts.service
journalctl -u bd-followup-drafts.service -o cat --since '2 min ago'
# vault_sync_guard REFUSING is correct; report it, do not bypass.

# 2. Second run each: Persistent=true catch-up on enable (LastTriggerUSec empty).
sudo systemctl enable --now bd-stall-radar.timer bd-followup-drafts.timer
# After= on the drafts unit serialises the two catch-ups through agent_propose.sh's flock.
# Read both journals. Then flip manifests.
```

`bin/deploy` after the tsv/docs edit (drift covers `config/`). No `--prune`. Do not stamp the timer files to suppress catch-up — that second fire **is** the second canary.

## Files to modify (after enable)

- `design/agents/claudius.toml` — both BD rows `status = "standing"`; trigger text; notes; `surfaces.scheduled.governed_by` grows the two BD runners.
- `config/fleet-units.tsv` — both `dormant` → `standing`.
- `docs/runbook.md` — drop the "do not enable a timer to create evidence" / dormant claims for these two.
- `config/job-overrides/README.md` — D1/T2.4 sentence becomes past tense.
- `design/eval-spec.md:166` — radar is no longer an uncovered dormant row (suite T2.3, enabled T2.4). Dated, not deleted as if it never was.

## Out of scope / do not touch

- `design/workflow-registry.md` — frozen (T6.4). The 09-01 "flip §4 rows" instruction does not apply.
- OnCalendar values, Stage/parked/no-Notion-writes guards, `AGENT_PROFILE` on the drafts example.
- `.claude/briefs/current.md` and `.claude/briefs/archive/`.
- `~/.config/agent-workforce/**`. Probe, do not peek.
- No `bin/deploy --prune`. No other timer.

## Notes

- Follow-up already ran once today (T2.2 canary, 09:52–10:01, proposal pushed, `owner=claudius`). That run does not count toward this gate; T2.4 still does two of its own.
- Radar last healthy run was 2026-08-13 (pre-T2.3 kernel path). Aug 31 was an OnFailure wiring probe that failed on purpose.
- `vault_sync_guard.sh check` was OK at 10:18 on 2026-09-09 (`origin/main` `855883e`). Re-check immediately before the drafts canary.
