#!/usr/bin/env bash
# Extract named sections from a markdown file, by heading text.
#
# Replaces the pinned `sed -n '19,36p;...'` reads that profiles used to carry (D3 part 1).
# Line numbers rot silently: the target file lives in the vault and the pins live in this
# repo, so no commit on either side can see the other move. Three of six ranges in
# profiles/augustus_content_task.md had drifted by 2026-09-02 — one dropping the self-check
# item the same profile promises by name, two opening mid-paragraph in a section the profile
# deliberately excludes. Nothing errored. Heading text drifts too, but it drifts LOUDLY:
# an unresolved name here is a non-zero exit and an empty stdout.
#
# Usage: skill_sections.sh <file> <section-heading-text>...
#
# A section name is the heading text EXACTLY as it appears in the file, without the leading
# `#`s — whole-string equality, never a prefix. `Step 2.5` is a prefix of `Step 2.55` and
# `Step 5` of both `Step 5.5` and `Step 5.6`, so a prefix matcher would over-match in
# silence, which is the class of bug this script exists to end.
#
# Extent is the heading line through the line before the next heading of the SAME OR HIGHER
# level, so a section carries its subsections. `## Variations mode` sits after three `###`
# archetypes and is the case that breaks a naive "stop at the next `###`" rule.
#
# All-or-nothing: every name must resolve to exactly one heading before anything is printed.
# A partial read is the failure being fixed — 8 of 9 sections is the same defect wearing a
# different mask — so an unresolved name prints to stderr and stdout stays empty.
#
# Exit: 0 all resolved and printed | 2 usage | 3 a name was absent or ambiguous.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $(basename "$0") <file> <section-heading-text>..." >&2
  exit 2
fi

file=$1
shift

if [ ! -r "$file" ]; then
  echo "$(basename "$0"): cannot read $file" >&2
  exit 2
fi

names=$(mktemp)
trap 'rm -f "$names"' EXIT
printf '%s\n' "$@" > "$names"

# Buffered into a variable rather than streamed, so a name that fails to resolve on the
# LAST line of the file cannot leave earlier sections already on stdout.
out=$(awk '
  FNR == NR { want[++n] = $0; next }

  { line[FNR] = $0 }

  /^(```|~~~)/ { fence = !fence; next }
  fence { next }

  /^#+ / {
    level = index($0, " ") - 1
    text  = substr($0, level + 2)
    sub(/[ \t]+$/, "", text)
    hstart[++h] = FNR; hlevel[h] = level; htext[h] = text
  }

  END {
    total = FNR
    for (i = 1; i <= n; i++) {
      hits = 0
      for (j = 1; j <= h; j++) if (htext[j] == want[i]) { hits++; pick[i] = j }
      if (hits == 0) { printf "unresolved (absent): %s\n", want[i] > "/dev/stderr"; bad = 1 }
      else if (hits > 1) { printf "unresolved (ambiguous, %d headings match): %s\n", hits, want[i] > "/dev/stderr"; bad = 1 }
    }
    if (bad) exit 3

    # File order, not argument order: the caller lists what it wants, the file decides
    # the sequence. Selection-sorted because n is single digits and awk has no sort.
    for (a = 1; a <= n; a++) {
      lo = 0
      for (i = 1; i <= n; i++) if (!done[i] && (lo == 0 || pick[i] < pick[lo])) lo = i
      done[lo] = 1
      j = pick[lo]
      stop = total
      for (k = j + 1; k <= h; k++) if (hlevel[k] <= hlevel[j]) { stop = hstart[k] - 1; break }
      for (r = hstart[j]; r <= stop; r++) print line[r]
    }
  }
' "$names" "$file") || exit 3

printf '%s\n' "$out"
