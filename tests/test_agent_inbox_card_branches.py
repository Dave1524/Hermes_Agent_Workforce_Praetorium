#!/usr/bin/env python3
"""Card branches are not Agent Inbox rows (Dev Plan B6, spec §3.7): `agents/<date>-card-<id>` is the
board's own landing branch and its only decision surface is the board, so the branch-row sync must
not qualify it. Beside tests/test_agent_inbox_branch_rows.py, which a ship rail keeps closed."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import agent_inbox_branch_rows as branch  # noqa: E402

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


print("--- card- branches are skipped by the branch-row predicate (::card-branches-skipped) ---")
check("a card branch does not qualify", not branch.is_branch_row("agents/2026-10-09-card-alpha-card"))
check("a slug that merely contains card does", branch.is_branch_row("agents/2026-10-09-discard-cards"))
check("a slug starting with card but no dash does", branch.is_branch_row("agents/2026-10-09-cardiac-review"))
check("an ordinary agent branch still qualifies", branch.is_branch_row("agents/2026-10-09-weekly-review"))
check("a nested card path does not", not branch.is_branch_row("agents/2026-10-09-card-x/evil"))

raise SystemExit(1 if failures else 0)
