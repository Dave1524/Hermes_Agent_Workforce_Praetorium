"""Assert a buzz-agent subscription DAG file admits exactly the expected authors.

Usage: check-rules.py <agent.toml> <pubkey> [<pubkey> ...]
Exits 0 when the file parses and its rules name exactly the given pubkeys.
"""

import re
import sys
import tomllib

AUTHOR_EQUALITY = re.compile(r'author\s*==\s*"([0-9a-f]{64})"')


def _authors(rules):
    for rule in rules:
        if not rule.get("require_mention"):
            raise ValueError(f"rule {rule.get('name')!r} does not require a mention")
        matches = AUTHOR_EQUALITY.findall(rule.get("filter", ""))
        if len(matches) != 1:
            raise ValueError(f"rule {rule.get('name')!r} is not a single author equality")
        yield matches[0]


def main(path, expected):
    with open(path, "rb") as handle:
        rules = tomllib.load(handle).get("rules", [])
    if not rules:
        raise ValueError("no [[rules]] found")
    found = sorted(_authors(rules))
    if found != sorted(expected):
        raise ValueError(f"admits {found}, expected {sorted(expected)}")


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"  {sys.argv[1]}: {error}", file=sys.stderr)
        sys.exit(1)
