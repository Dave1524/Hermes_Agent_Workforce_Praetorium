"""Assert a buzz-agent subscription DAG file admits exactly the expected authors,
on exactly the expected terms.

Usage: check-rules.py <agent.toml> <spec> [<spec> ...]

A spec is either:
  <pubkey>        the author is admitted UNCONDITIONALLY — no rule for them may
                  carry a hop token
  <pubkey>@hop    the author is admitted ONLY through hop-gated rules — every rule
                  naming them must carry one, and its value must be in HOP_BUDGET

The `@hop` form exists because marcus gained a return edge on 2026-09-07: workers
may now wake him, which closes a cycle the DAG previously left open. The bound is a
hop token in the body, and asserting the SET of admitted authors is no longer
enough — an edit that admitted the same three workers unconditionally would pass a
set check while removing the only thing bounding the chain. So the terms are
asserted too, and HOP_BUDGET is asserted here rather than trusted to a comment:
adding a `[hop:6]` rule is the documented way this stops bounding anything, and it
now fails the gate instead of being a sentence someone has to remember.
"""

import re
import sys
import tomllib

AUTHOR_EQUALITY = re.compile(r'author\s*==\s*"([0-9a-f]{64})"')
HOP_TOKEN = re.compile(r'str_contains\s*\(\s*content\s*,\s*"\[hop:(\d+)\]"\s*\)')

# The admitted return hops. Marcus dispatches on 1 and 3; a worker answers on 2 and
# 4, and 4 is its last word. Widening this set widens the chain.
HOP_BUDGET = {2, 4}


def _edges(rules):
    """Yield (author, hop_or_None) for every rule, validating rule shape."""
    for rule in rules:
        name = rule.get("name")
        if not rule.get("require_mention"):
            raise ValueError(f"rule {name!r} does not require a mention")
        expr = rule.get("filter", "")
        authors = AUTHOR_EQUALITY.findall(expr)
        if len(authors) != 1:
            raise ValueError(f"rule {name!r} is not a single author equality")
        hops = HOP_TOKEN.findall(expr)
        if len(hops) > 1:
            raise ValueError(f"rule {name!r} carries {len(hops)} hop tokens, expected at most 1")
        yield authors[0], (int(hops[0]) if hops else None)


def main(path, specs):
    with open(path, "rb") as handle:
        rules = tomllib.load(handle).get("rules", [])
    if not rules:
        raise ValueError("no [[rules]] found")

    expected = {}
    for spec in specs:
        key, _, mode = spec.partition("@")
        expected[key] = mode or None

    seen = {}
    for author, hop in _edges(rules):
        seen.setdefault(author, []).append(hop)

    if sorted(seen) != sorted(expected):
        raise ValueError(f"admits {sorted(seen)}, expected {sorted(expected)}")

    for author, hops in sorted(seen.items()):
        gated = expected[author] == "hop"
        if gated:
            if any(h is None for h in hops):
                raise ValueError(f"author {author} must be hop-gated but has an ungated rule")
            out = sorted(h for h in hops if h not in HOP_BUDGET)
            if out:
                raise ValueError(
                    f"author {author} admitted at hop(s) {out}, outside budget {sorted(HOP_BUDGET)}"
                )
        elif any(h is not None for h in hops):
            raise ValueError(f"author {author} must be unconditional but has a hop-gated rule")


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"  {sys.argv[1]}: {error}", file=sys.stderr)
        sys.exit(1)
