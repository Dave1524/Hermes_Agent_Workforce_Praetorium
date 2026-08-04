#!/usr/bin/env python3
"""Render the bounded NIP-01 note that points back at a delivered Buzz channel message.

The budget is UTF-8 BYTES, not characters: 800 characters of accented prose is ~1.2 KB
on the wire, so a character budget would silently overshoot. Two rules follow from what
the note is *for* — it is a pointer, not a copy:

  * the attribution and channel-pointer lines are reserved out of the budget BEFORE the
    body is measured, so a truncated note still says who produced it and where the full
    artifact lives. A note whose pointer was cut looks like a delivery receipt and links
    nowhere, which is worse than publishing nothing.
  * every cut lands on a codepoint boundary, so truncation can never emit invalid UTF-8.

usage: buzz_note.py --headline TEXT --job UNIT --runtime NAME --pointer URL
                    [--digest LINE]... [--max-bytes N] [--max-digest-lines N]
"""
import argparse
import sys

ELLIPSIS = "…"


def fit(text, budget):
    """Longest codepoint-aligned prefix of `text` fitting `budget` UTF-8 bytes."""
    raw = text.encode("utf-8")
    if len(raw) <= budget:
        return text
    if budget <= 0:
        return ""
    marker = ELLIPSIS if len(ELLIPSIS.encode("utf-8")) < budget else ""
    room = budget - len(marker.encode("utf-8"))
    return raw[:room].decode("utf-8", "ignore") + marker


def render(headline, digest, job, runtime, pointer, max_bytes, max_digest_lines):
    tail = "job: {} · runtime: {}\n{}".format(job, runtime, pointer)
    budget = max_bytes - len(tail.encode("utf-8")) - 1
    body = []
    for candidate in [headline] + list(digest)[:max_digest_lines]:
        candidate = candidate.strip()
        if not candidate or budget <= 0:
            continue
        line = fit(candidate, budget)
        if not line:
            break
        body.append(line)
        budget -= len(line.encode("utf-8")) + 1
    return "\n".join(body + [tail])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--headline", default="")
    p.add_argument("--digest", action="append", default=[])
    p.add_argument("--job", default="unknown")
    p.add_argument("--runtime", default="unknown")
    p.add_argument("--pointer", default="")
    p.add_argument("--max-bytes", type=int, default=800)
    p.add_argument("--max-digest-lines", type=int, default=4)
    a = p.parse_args()
    sys.stdout.write(
        render(a.headline, a.digest, a.job, a.runtime, a.pointer,
               a.max_bytes, a.max_digest_lines)
    )


if __name__ == "__main__":
    main()
