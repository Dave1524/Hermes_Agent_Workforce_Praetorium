#!/usr/bin/env python3
"""Append one structured delivery receipt (a single JSON object) to a JSONL file.

The receipt file is the ONLY evidence the seven-day dual-run audit accepts: green
systemd units and quiet error logs both stayed green through the two live failures
that predate this migration, because "the unit exited 0" and "the output reached a
human" are different claims. Every invocation of bin/deliver.sh writes exactly one
line here, including the ones that deliberately sent nothing.

Redaction happens here rather than at each call site so there is one place to audit.

usage: delivery_receipt.py --path FILE key=value [key=value ...]
"""
import argparse
import datetime
import json
import re
import sys

SCHEMA = 1

SECRET_PATTERNS = [
    (re.compile(r"nsec1[02-9ac-hj-np-z]{10,}"), "[redacted]"),
    (re.compile(r"(private[_-]?key|auth[_-]?tag|api[_-]?key|token)"
                r"(\"?\s*[:=]\s*\"?)([^\s\"',]+)", re.I), r"\1\2[redacted]"),
]


def scrub(text):
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


NUMERIC_SUFFIXES = ("_bytes", "_secs", "_count")


def coerce(key, value):
    if value in ("true", "false"):
        return value == "true"
    if value == "null":
        return None
    # Numeric coercion is opt-in by key. A 64-hex event id can be all digits, and
    # int()-ing it turns a Nostr identifier into a JSON number that has lost its
    # leading zeros — the auditor would then never match it against the relay.
    if key.endswith(NUMERIC_SUFFIXES) and re.fullmatch(r"-?\d+", value):
        return int(value)
    return scrub(value)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--path", required=True)
    p.add_argument("pairs", nargs="*")
    a = p.parse_args()

    receipt = {
        "schema": SCHEMA,
        "ts": datetime.datetime.now(datetime.timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    for pair in a.pairs:
        key, _, value = pair.partition("=")
        if key:
            receipt[key] = coerce(key, value)

    try:
        with open(a.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    except OSError as exc:
        sys.stderr.write("delivery_receipt: cannot append to {}: {}\n".format(a.path, exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
