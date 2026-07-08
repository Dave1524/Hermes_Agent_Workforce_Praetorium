# NUC-23 AC2 — Approval outcomes (MAC-SIDE deferral spec)

**Status: not implemented on Praetorium.** AC2 targets the *canonical* vault repo
(`~/dev/obsidian-ai-os`, `00_system/tools/agent_inbox.py`), which lives **only on the Mac** —
this box has just the box-safe projection (`vault-boxsafe`, no `agent_inbox.py`). Apply this on
the Mac; its gate is `python3 00_system/tools/agent_inbox_test.py`.

The box side already ships standalone: `bin/scorecard.sh` reads the approvals feed and reports
`pending (awaiting Mac sync)` until this lands, then flips to real counts automatically.

## Contract (box-safe)

On `promote` / `reject`, append **one line** to the box-safe metrics file the box scorecard reads:

```
_inbox/agents/_metrics/approvals.tsv
```

Line format (append-only; only these three keys — no proposal body, no client-identifiable
strings, no `_confidential/` content — the slug is the already-published de-identified proposal
filename):

```
ts=<ISO8601 UTC>  slug=<proposal-slug>  decision=<promoted|rejected|edited>
```

`decision=edited` = the promotion modified the proposal body before applying it (a weaker-trust
signal than a clean promote); `promoted` = applied as-is; `rejected` = discarded.

## Implementation (`00_system/tools/agent_inbox.py`)

Add a helper and call it from the promote/reject paths:

```python
def record_approval_outcome(slug: str, decision: str) -> None:
    """Append one box-safe approval-outcome line to _inbox/agents/_metrics/approvals.tsv,
    then git add/commit/push it to the agents branch the box pulls. Fail-soft."""
    # 1. ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # 2. mkdir -p <boxsafe-worktree>/_inbox/agents/_metrics/
    # 3. append: f"ts={ts}\tslug={slug}\tdecision={decision}\n"   (only these keys)
    # 4. git add that file; commit "metrics: approval outcome {slug}"; push to `agents`.
    #    (agent_propose.sh line 39 `git pull --ff-only origin agents/inbox` brings it to the box;
    #     scorecard.sh then reports real promoted/rejected/edited counts.)
```

- Call `record_approval_outcome(slug, "promoted")` (or `"edited"`) on the promote path.
- Call `record_approval_outcome(slug, "rejected")` on the reject path.

## Tests (`agent_inbox_test.py`, TDD — red first)

- `test_promote_records_outcome` — a line with the slug + `decision=promoted`.
- `test_reject_records_outcome` — `decision=rejected`.
- `test_edited_records_outcome` — `decision=edited`.
- `test_append_only` — two decisions → two lines, no overwrite.
- `test_record_box_safe` — the line contains ONLY `ts`/`slug`/`decision`; no body / no
  `_confidential` markers / no client-identifiable strings.

## Why this matters

The approvals feed is the **trust-maturity signal** NUC-20 needs before ratifying the Phase-2
roster (promote/reject/edit rates drive the approval matrix). The box scorecard already surfaces
it — this is the only missing producer.
