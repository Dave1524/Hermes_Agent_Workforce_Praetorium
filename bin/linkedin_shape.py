#!/usr/bin/env python3
"""Measure a LinkedIn post against the shape spec in profiles/linkedin_shape.md.

Prints a per-metric verdict and the exact `Shape:` line the polish profile requires.
Exit 0 when every metric passes, 1 when any FAILs. WARNs do not fail: a post may sit
outside a band on purpose, and the profile asks for the reason on the Watch line.
"""
import re
import sys

HARD_MAX = 3000
BAND = (1300, 1900)
ULTRA = 2000
HOOK_LINE_MAX = 140
FOLD = 210
SENTENCE_WORDS = 15
BLOCK_SENTENCES = 3
THIN_BLOCK_CHARS = 70
THIN_BLOCK_SHARE = 0.7


def split_blocks(text):
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def split_sentences(text):
    return [s for s in (s.strip() for s in re.split(r"(?<=[.!?])\s+", text)) if s]


def strip_hashtags(text):
    return re.split(r"\n\s*(?:Hashtags:|#\w)", text)[0].strip()


def verdict(ok, warn=False):
    return "WARN" if warn and not ok else ("PASS" if ok else "FAIL")


def report(label, value, note, state):
    print(f"  {state:4}  {label:<22} {value:<12} {note}")
    return state


def check_length(body, full):
    n = len(body)
    if n > HARD_MAX:
        return report("total (body)", f"{n} chars", f"over LinkedIn's {HARD_MAX} limit", "FAIL")
    if BAND[0] <= n <= BAND[1]:
        return report("total (body)", f"{n} chars", f"in the {BAND[0]}-{BAND[1]} band", "PASS")
    if n >= ULTRA:
        return report("total (body)", f"{n} chars", "ultra-long tier - justify on Watch", "WARN")
    return report("total (body)", f"{n} chars", f"under {BAND[0]} - short-form only", "WARN")


def check_hook(blocks):
    first_line = blocks[0].split("\n")[0] if blocks else ""
    state = report("hook line 1", f"{len(first_line)} chars",
                   f"target <{HOOK_LINE_MAX}, must stand alone",
                   verdict(len(first_line) <= HOOK_LINE_MAX, warn=True))
    above_fold = "\n\n".join(blocks[:2])[:FOLD]
    truncated = len("\n\n".join(blocks[:2])) > FOLD
    report("above the fold", f"{min(len(above_fold), FOLD)} chars",
           "cut mid-thought at 210" if truncated else "hook+re-hook fit above the fold",
           verdict(not truncated, warn=True))
    return state


def check_blocks(blocks):
    if not blocks:
        return report("paragraph blocks", "0", "empty post", "FAIL")
    fat = [b for b in blocks if len(split_sentences(b)) > BLOCK_SENTENCES]
    state = report("paragraph blocks", str(len(blocks)),
                   f"{len(fat)} over {BLOCK_SENTENCES} sentences",
                   verdict(not fat))
    thin = [b for b in blocks if len(b) < THIN_BLOCK_CHARS]
    share = len(thin) / len(blocks)
    report("chars per block", f"{sum(len(b) for b in blocks) // len(blocks)} avg",
           f"{share:.0%} of blocks are one short line"
           + (" - staccato, merge into 1-2 sentence thoughts" if share > THIN_BLOCK_SHARE else ""),
           verdict(share <= THIN_BLOCK_SHARE, warn=True))
    return state


def check_sentences(body):
    longs = [s for s in split_sentences(body) if len(s.split()) > SENTENCE_WORDS]
    return report("long sentences", str(len(longs)),
                  f"over {SENTENCE_WORDS} words" + (f" - first: {longs[0][:48]!r}" if longs else ""),
                  verdict(not longs, warn=True))


def check_close(blocks):
    close = blocks[-1] if blocks else ""
    bait = re.search(r"\b(thoughts|agree|who else|am i wrong|drop a|comment below)\b\??\s*$",
                     close, re.I)
    if bait:
        return report("close", "engagement bait", f"{close[-40:]!r} - ai_tells #11", "FAIL")
    return report("close", "question" if close.rstrip().endswith("?") else "statement",
                  "one genuine operator question preferred",
                  verdict(close.rstrip().endswith("?"), warn=True))


def main(argv):
    if len(argv) != 2:
        print("usage: linkedin_shape.py POST.txt", file=sys.stderr)
        return 2
    with open(argv[1]) as handle:
        full = handle.read().strip()
    body = strip_hashtags(full)
    blocks = split_blocks(body)

    print(f"shape check: {argv[1]}")
    states = [check_length(body, full), check_hook(blocks), check_blocks(blocks),
              check_sentences(body), check_close(blocks)]
    first_line = blocks[0].split("\n")[0] if blocks else ""
    print(f"\nShape: {len(body)} chars, hook {len(first_line)}, "
          f"{len(blocks)} blocks — from linkedin_shape.py, not estimated")
    return 1 if "FAIL" in states else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
