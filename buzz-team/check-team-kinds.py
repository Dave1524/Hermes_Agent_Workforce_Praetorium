"""Assert the channel table in TEAM.md agrees with the deployed route table.

Usage: check-team-kinds.py [<buzz_routes.env>] [<TEAM.md>]
Exits 0 when every routed channel appears in the TEAM.md table under the same event kind.

The kind a channel renders is one fact with two readers — deliver.sh resolves
ROUTE_<key>_kind for scheduled output, agents read the TEAM.md table for everything they
send by hand. Disagreement is invisible at runtime: the wrong kind is accepted by the
relay, receipted `ok`, and rendered to nobody. buzz_routes.env is the owner; this only
catches TEAM.md falling behind it.
"""

import re
import sys
from pathlib import Path

# The DEPLOYED route table, not the git working tree — that is the one deliver.sh runs.
DEFAULT_ROUTES = Path.home() / "agent-workforce/bin/buzz_routes.env"
DEFAULT_TEAM = Path.home() / ".config/buzz-team/TEAM.md"
DEFAULT_KIND = 9

ROUTE = re.compile(r"^ROUTE_([a-z][a-z0-9_-]*)=(\S+)$", re.M)
ROUTE_KIND = re.compile(r"^ROUTE_([a-z][a-z0-9_-]*)_kind=(\d+)$", re.M)
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _routed_kinds(text):
    kinds = {key: int(kind) for key, kind in ROUTE_KIND.findall(text)}
    return {
        uuid: kinds.get(key, DEFAULT_KIND)
        for key, uuid in ROUTE.findall(text)
        if not key.endswith(("_kind", "_notify"))
    }


def _documented_kinds(text):
    documented = {}
    for row in text.splitlines():
        uuid = UUID.search(row)
        if "|" not in row or not uuid:
            continue
        # The kind is whatever number the last cell names: "9 — no `--kind`" or "`--kind 45001`".
        # Scanned right-to-left but STOPPED AT THE UUID CELL, because a UUID is 32 hex digits
        # and always matches \d+. Without the stop, a row whose kind cell holds no number
        # falls through to the UUID and "documents" whatever digit run starts it — so a row
        # missing its kind entirely resolved to 9 for every UUID beginning 9 followed by a
        # hex letter, and passed as agreeing with the stream default. The `else None` branch
        # below was unreachable for the same reason, which is what hid it.
        cells = row.split("|")
        after_uuid = cells[next(i for i, cell in enumerate(cells) if UUID.search(cell)) + 1:]
        numbers = (re.search(r"\d+", cell) for cell in reversed(after_uuid))
        kind = next((match for match in numbers if match), None)
        documented[uuid.group()] = int(kind.group()) if kind else None
    return documented


def _drift(routed, documented):
    for uuid, kind in sorted(routed.items()):
        if uuid not in documented:
            yield f"{uuid} is routed as kind {kind} and is absent from the TEAM.md table"
        elif documented[uuid] is None:
            yield f"{uuid} is routed as kind {kind} and its TEAM.md row names no kind"
        elif documented[uuid] != kind:
            yield f"{uuid} is kind {kind} in buzz_routes.env, {documented[uuid]} in TEAM.md"
    for uuid in sorted(set(documented) - set(routed)):
        yield f"{uuid} is in the TEAM.md table but names no route"


def main(routes, team):
    drift = list(_drift(_routed_kinds(routes.read_text()), _documented_kinds(team.read_text())))
    if drift:
        raise ValueError("; ".join(drift))


if __name__ == "__main__":
    paths = sys.argv[1:] or [DEFAULT_ROUTES, DEFAULT_TEAM]
    try:
        main(*(Path(path) for path in paths))
    except (OSError, TypeError, ValueError) as error:
        print(f"  {error}", file=sys.stderr)
        sys.exit(1)
