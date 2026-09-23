# Brief: T9.1 — fixture
**Date:** 2026-09-20   **Verify:** `bash bin/verify.sh`

## Acceptance criteria
- `bin/not-a-file-section.sh` — a path outside the Files sections is not named.

## Files to modify
- `bin/a.sh:12` — the change.
- `bin/never.sh` — named, never touched.
- `.claude/briefs/t9-1-fixture.md` — this brief names itself; not counted.

## Files to create
- `tests/test_a.sh` — its test.

## Files to delete
- `bin/old.sh` — retired.

## Test plan
- `tests/test_a.sh`.
