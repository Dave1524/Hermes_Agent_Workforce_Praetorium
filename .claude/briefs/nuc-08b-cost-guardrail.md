# Brief: NUC-08b cost/runaway-loop guardrail — close remaining gaps
**Date:** 2026-07-07   **Verify:** `bash bin/verify.sh`

## Acceptance criteria
1. `agent_propose.sh` logs a cost/run line to `logs/cost.log` on **every** invocation —
   including runs that exhaust all retry attempts and fail — not only successful or
   clean-no-proposal runs. Today the log line sits after the failure branch's `exit 1`,
   so failed runs are invisible to cost tracking.
2. `AGENT_MAX_ITERATIONS` (from `secrets.env`) is actually enforced on the Hermes
   invocation via the `hermes --max-turns` CLI flag (confirmed to exist:
   `hermes_cli/_parser.py:343`, overrides `agent.max_turns` in profile config), so it
   becomes the single enforced ceiling instead of silently-unused dead config sitting
   next to the hardcoded `max_turns: 24` in
   `~/.hermes/profiles/research_analyst/config.yaml`.
3. `AGENT_MAX_CALLS_PER_RUN` is either wired to a real enforcement point (if one exists
   in hermes) or explicitly documented as **not yet enforced** — do not leave it looking
   load-bearing if it silently does nothing.
4. A smoke test exercises `agent_propose.sh` end-to-end with a mocked `AGENT_RUNTIME_CMD`
   (no real API calls, no spend) and proves: cost.log gets a line on both the success and
   the failure path; the write-boundary check still aborts + resets the worktree when a
   file outside `_inbox/agents/**` changes; the `--max-turns` flag is actually present in
   the effective invocation.
5. No secrets, real API keys, or the `.confidential` tree are read, written, or logged.
6. `bash bin/verify.sh` stays green.

## Files to modify
- `bin/agent_propose.sh` — restructure so the `logs/cost.log` append happens
  unconditionally (e.g. via a function called from both the success and failure paths,
  or a `trap ... EXIT`), recording at minimum `run_seconds`, `attempts`, and an
  `outcome=OK|FAIL` field. Also append `--max-turns "${AGENT_MAX_ITERATIONS:?AGENT_MAX_ITERATIONS not set}"`
  to the `AGENT_RUNTIME_CMD` invocation (fail loud if the env var is missing, consistent
  with the script's existing preflight-gate style).

## Files to create
- `tests/test_agent_propose_smoke.sh` — mocks `AGENT_RUNTIME_CMD`/`hermes` (a stub script
  that just echoes its argv to a file and exits 0 or 1 as directed) and a scratch worktree
  standing in for `~/agent-worktrees/inbox`, then runs `agent_propose.sh` under each
  scenario below and asserts on `logs/cost.log` / exit code / worktree state:
  1. mocked runtime exits 0, no worktree changes → "no proposal" log line + a cost.log line.
  2. mocked runtime exits 1 every attempt → all 3 retries exhausted, worktree reset,
     script exits 1, **and** a cost.log line with `outcome=FAIL` is still written.
  3. mocked runtime writes a file outside `_inbox/agents/**` → FATAL log, worktree reset,
     nothing pushed.
  4. assert the captured argv from the mocked runtime includes `--max-turns <value>`
     matching `AGENT_MAX_ITERATIONS`.
  Must not require network access or a real API key.

## Test plan
- `bash bin/verify.sh` (runs syntax + shellcheck + everything under `tests/*.sh`,
  including the new smoke test) — must exit 0.
- No live run against the real `research_analyst` profile / real OpenRouter key as part
  of this brief — the smoke test's mocked runtime is the substitute, since
  `agent_propose.sh` has never actually executed on this box and a first real run isn't
  this task's job (that's NUC-16's).

## Out of scope / do not touch
- Do **not** enable `agent-proposal.timer`/`.service` (`systemctl enable`) — that switch
  is NUC-16's call once this guardrail is verified, not this brief's.
- Do not touch `~/.confidential.img`, `._confidential_mount`, or anything under
  `~/.config/agent-workforce/` beyond documenting the `--max-turns` behavior change in a
  comment (that directory is outside this git repo by design — see this repo's CLAUDE.md
  "Secrets are a separate tree").
- Do not modify Hermes tool code under `~/.hermes/hermes-agent/` — that's upstream, not
  ours.
- Do not invent an enforcement mechanism for `AGENT_MAX_CALLS_PER_RUN` if none exists in
  hermes — document the gap instead of guessing.

## Notes / preconditions
- Confirmed live on the box (2026-07-07): `OPENROUTER_API_KEY` set; OpenRouter per-key
  hard credit cap set to **$25/month** in the provider dashboard (this was the last open
  NUC-08b blocker, now resolved — Notion card moved Blocked → In progress); `AGENT_RUNTIME_CMD`
  set and points at the `research_analyst` Hermes profile; inbox worktree exists at
  `~/agent-worktrees/inbox`; `agent-proposal.timer`/`.service` are installed but correctly
  left `disabled`/`inactive` pending this task.
- `AGENT_MAX_ITERATIONS` / `AGENT_MAX_CALLS_PER_RUN` exist in `secrets.env` today but are
  not read by any script — confirmed via grep across `~/agent-workforce` and `~/.hermes`.
  This is the "one concept, two owners" bug this brief closes for `AGENT_MAX_ITERATIONS`.
- `secrets.env` lives at `~/.config/agent-workforce/secrets.env`, **outside** this git
  repo — never `git add` it; any live comment/documentation update to it happens directly
  on the box, not via a commit here.
- `agent_propose.sh` has never actually run on this box (no prior `agent_propose.log` /
  `agent_run.log` / `cost.log`) — this brief's smoke test will be its first real exercise,
  deliberately mocked rather than live.
- Baseline commit `2872470` in `~/dev/agent-workforce` captures the current live state
  (verbatim, no behavior changes) with `bin/verify.sh` as the Verification gate — this
  brief's diff should apply cleanly on top of it.
