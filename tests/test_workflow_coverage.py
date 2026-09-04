#!/usr/bin/env python3
"""
Workflow-coverage report and problem list. Driven from tests/test_workflow_coverage.sh.

Emits a human report on stdout, and one machine line per problem:

    PROBLEM<TAB><assertion-id><TAB><detail>
    EXEMPT<TAB><unit><TAB><reason>
    SUMMARY<TAB>key=value ...

The .sh asserts over those tags. Exit status is always 0 — the caller decides, so that a
run which finds five problems still prints all five instead of dying on the first.

THE JOIN IS DECLARED, NOT INFERRED (D6). Ownership is read from two sources, in both
directions: design/agents/*.toml `[[workflows]] suite = [...]` gives workflow -> suite, and
design/fleet-suites.toml gives suite -> "fleet" for the suites no workflow can ever claim.
Reading only the first direction reports tests/test_fleet_guards.sh as an orphan, and an
orphan's recommended fix is deletion.
"""
import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUSES = {"standing", "campaign", "spent", "dormant", "planned"}
DECLARES_WORKFLOWS = re.compile(r"^\s*\[\[workflows\]\]\s*$", re.M)
EXEC_LINE = re.compile(r"^\s*Exec[A-Za-z]*=")
BIN_REF = re.compile(r"bin/[A-Za-z0-9_.@-]+(?:/[A-Za-z0-9_.@-]+)*")
# The assertion-id anchor: a `::`-prefixed id wrapped in parentheses. Deliberately the same
# notation design/agents/*.toml already uses on the other side of the colons in
# `test = "<suite>::<id>"`, which tests/test_fleet_guards.sh's enforced-has-test greps back.
# The parentheses are what separate a DECLARATION site from a mention: cross-references in
# prose are written `<path>::<id>` with no brackets, so they are not mistaken for anchors.
ANCHOR = re.compile(r"\(::([A-Za-z0-9][A-Za-z0-9_-]*)\)")
COMPANION = re.compile(r"tests/[A-Za-z0-9_.-]+\.py")
# python named in COMMAND POSITION, not merely somewhere on the line. Matching the word
# anywhere credits a comment that mentions the interpreter as a hand-off to it — see
# suite_sources.
PY_INVOKE = re.compile(r"(?:^|[;&|]\s*|\bexec\s+)python3?\s")

problems = []
exempt = []


def problem(assertion, detail):
    problems.append((assertion, detail))


def bin_refs(text):
    """bin/ paths named in text that are real files here.

    The existence requirement is the whole guard: `#!/usr/bin/env bash` yields "bin/env",
    prose yields a trailing period ("bin/agent_inbox_notion_sync.py."), and an out-of-repo
    absolute path yields its tail (".local/bin/holiday-content-reminder-20260831.sh").
    None of the three is a file under bin/.
    """
    found = set()
    for match in BIN_REF.findall(text):
        candidate = match.rstrip(".,;:)\"'")
        if (ROOT / candidate).is_file():
            found.add(candidate)
    return found


def units(archived):
    """*.service under systemd/, with systemd/archive/ split off by an EXPLICIT filter.

    Takes the boolean, not a path. The parameter used to be a directory string that was
    only ever inspected for the word "archive" and never scoped the glob, so
    units("systemd/user") would have returned the whole non-archive set and read as
    correct.

    Stated rather than inherited from a `*` someone widens later. It is still only a
    convention — measured 2026-09-02, counting archive/ as live empties the retired set and
    the one true orphan disappears, under both a widened glob and a deleted filter. So the
    exclusion is not left to hold on its own: see the archive-exclusion guard below, which
    is what turns that mutation into a red instead of a quiet green.
    """
    return [p for p in sorted(ROOT.glob("systemd/**/*.service"))
            if ("archive" in p.relative_to(ROOT).parts) == archived]


def exec_subjects(unit_files):
    """bin/ scripts named on any Exec* line. ExecStartPost= carries five delivery scripts
    that appear on no ExecStart= line anywhere, so the prefix must stay open."""
    subjects = set()
    for unit in unit_files:
        for line in unit.read_text().splitlines():
            if EXEC_LINE.match(line):
                subjects |= bin_refs(line)
    return subjects


# --- parse ---------------------------------------------------------------------------
entries = []
manifests = sorted((ROOT / "design" / "agents").glob("*.toml"))
for manifest in manifests:
    text = manifest.read_text()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        problem("parse-integrity", f"{manifest.name}: does not parse: {exc}")
        continue
    parsed = data.get("workflows", [])
    # Anchored to a table-array header, never to the text: aurelian.toml carries the string
    # in a comment ("# No [[workflows]]. Intentionally.") and owns nothing by design.
    if DECLARES_WORKFLOWS.search(text) and not parsed:
        problem("parse-integrity",
                f"{manifest.name}: declares [[workflows]] but parsed 0 entries")
    entries += [(manifest.stem, w) for w in parsed]

if not entries:
    problem("parse-integrity",
            f"0 workflow entries parsed from {len(manifests)} manifests — "
            "a coverage figure computed from nothing")

for owner, w in entries:
    if w.get("status") not in STATUSES:
        problem("parse-integrity",
                f"{w.get('unit')} ({owner}): status {w.get('status')!r} is outside "
                f"{sorted(STATUSES)}")

standing = [(o, w) for o, w in entries if w.get("status") == "standing"]
if entries and not standing:
    problem("parse-integrity",
            f"the status filter selected 0 of {len(entries)} parsed entries — "
            "a filter that matches nothing has computed nothing")

# --- coverage ------------------------------------------------------------------------
covered, uncovered = [], []
for owner, w in standing:
    unit = w.get("unit")
    if w.get("suite_exempt"):
        # The skip and the print are one fact, so a silent exemption cannot be written.
        exempt.append((unit, w["suite_exempt"]))
        continue
    # Length, not key presence: all entries carry `suite`, and today ten carry `suite = []`.
    # An `in` / has_key test passes every one of them and reports full coverage.
    if len(w.get("suite") or []) >= 1:
        covered.append((owner, unit))
    else:
        uncovered.append((owner, unit))
        problem("standing-has-suite",
                f"{unit} ({owner}): status = \"standing\", no suite_exempt, names no suite")

claimed = set()
for owner, w in entries:
    for path in w.get("suite") or []:
        claimed.add(path)
        if not (ROOT / path).is_file():
            problem("suite-paths-exist",
                    f"{w.get('unit')} ({owner}): declared suite {path} is not a file")

# design/fleet-suites.toml's own SCHEMA is asserted by tests/test_fleet_guards.sh (path
# exists, owner is in the enum, asserts non-empty). Consumed here, not re-validated. The
# `asserts` JOIN below is a different claim from that schema and lives here deliberately —
# see the block that opens it.
decl = ROOT / "design" / "fleet-suites.toml"
fleet_declared, fleet_owned = set(), set()
fleet_entries = []
if decl.is_file():
    for suite in tomllib.loads(decl.read_text()).get("suite", []):
        fleet_declared.add(suite.get("path"))
        fleet_entries.append((suite.get("path"), list(suite.get("asserts") or [])))
        if suite.get("owner"):
            fleet_owned.add(suite.get("path"))
claimed |= fleet_owned

# --- orphans -------------------------------------------------------------------------
# Retirement is DECLARED, not inferred. Two static reachability rules were measured over
# bin/ on 2026-09-02: "any textual reference" leaves 37 scripts unreachable and MISSES the
# one true orphan (bin/notion_rest.py:241 names it in a comment); "comment lines stripped"
# leaves 46 and finds it. Scoped to the unclaimed suites they still fire 20 and 23 false
# positives — libraries, interactive tools, and bin/verify.sh itself, which no unit execs.
# So the subject comes from the archived unit's own ExecStart line instead: moving a unit
# into systemd/archive/ is the act that retires its script, and it is recorded in-repo.
archived_subjects = exec_subjects(units(archived=True))
retired = archived_subjects - exec_subjects(units(archived=False))

# The archive-exclusion guard. Subtracting live execs is the correct rule and it is also
# the rule's single point of failure: let archive/ into the live set and `retired` empties,
# every orphan check passes, and the run reads exactly like a clean one. An input that can
# no longer produce a finding must say so rather than report nothing found.
if archived_subjects and not retired:
    problem("no-orphan-suite",
            f"systemd/archive/ execs {', '.join(sorted(archived_subjects))} yet nothing "
            "reads as retired — the archive exclusion is not in force and the orphan rule "
            "is asserting nothing")

suites = sorted(f"tests/{p.name}" for p in ROOT.glob("tests/test_*.sh"))
unclaimed = [s for s in suites if s not in claimed]
orphans = []
# The suite -> fleet direction, asserted as a JOIN rather than as a schema — the file's own
# structure is tests/test_fleet_guards.sh's job. A path named here that the join does not
# credit is owned by nothing: reading only workflow -> suite is what puts the fleet's
# security suite in the orphan bucket, and an orphan's recommended fix is deletion.
for path in sorted(fleet_declared - fleet_owned):
    orphans.append((path, []))
    problem("no-orphan-suite",
            f"{path}: named in design/fleet-suites.toml but the entry confers no owner, "
            "so nothing claims it in either direction")

for suite in unclaimed:
    text = (ROOT / suite).read_text()
    pair = ROOT / suite.replace(".sh", ".py")
    if pair.is_file():
        text += pair.read_text()
    dead = sorted(bin_refs(text) & retired)
    if dead:
        orphans.append((suite, dead))
        problem("no-orphan-suite",
                f"{suite}: claimed by no workflow and no fleet owner, and its subject "
                f"{', '.join(dead)} is exec'd only by an archived unit")

# --- the asserts join (W9) -----------------------------------------------------------
# Until 2026-09-04 design/fleet-suites.toml's `asserts` list named its assertions by
# CONVENTION ONLY. Nothing read the strings: this file read `path` and `owner` and never
# `asserts`, and tests/test_fleet_guards.sh only checked the list was non-empty. So renaming
# an id on either side left the other silently stale — one fact in two places, which is the
# class D6 exists to detect, sitting inside D6's own join.
#
# THERE WAS NO SECOND SHAPE TO PRESERVE, which is the measurement that decided the fix.
# Counted across the four entries, 2026-09-04: 32 declared ids, of which 8 were anchored
# (all in tests/test_fleet_guards.sh), 5 appeared as `check <id>` calls in
# tests/test_workflow_coverage.sh, and 19 appeared NOWHERE in the files they name — not as
# an id, not as a description. tests/test_fleet_ownership.sh declared nine ids against seven
# prose group headers; tests/test_content_inbox_finalize.sh declared nine against thirteen,
# in a file it does not even contain (it is an eight-line wrapper round a .py). A per-entry
# `kind` would have blessed that gap as a second legitimate shape. It was one shape and
# three files that had not adopted it, so the anchor was added to all of them instead.
#
# BOTH DIRECTIONS, because either alone fails open. A declared id with no anchor catches a
# rename inside the suite; an anchor no entry declares catches a rule added to a suite that
# never reached the manifest, and a rename onto an id that happens to be declared elsewhere.
#
# AND A VACUITY GUARD, because this join's own failure mode is reaching nothing: an entry
# whose files yield zero anchors passes every comparison it never makes, exactly as
# test_fleet_ownership.sh's kind join does when pointed at the wrong root.
#
# WHAT IT DOES NOT CLAIM. It joins ids to anchors, not assertions to ids. A group carrying
# no anchor is outside the join and is not reported — test_content_inbox_finalize.py has
# thirteen groups and nine declared rules, and the four unnamed ones stay unnamed. Widening
# that would make the manifest enumerate every echo, which is not what `asserts` is for.
# Stated here so the rule's reach is readable, the way no-orphan-suite's is.
#
# EDITING TRAP: a parenthesised `::`-id written as an EXAMPLE in any scanned file becomes a
# real anchor. It fails loudly — an anchor no entry declares — rather than silently, which
# is why the form is described in words above and never shown as a literal.


def suite_sources(path):
    """The declared file, plus any tests/*.py it hands the whole run to.

    Two of the declared suites are thin wrappers: tests/test_content_inbox_finalize.sh is
    eight lines ending in `exec python3 tests/test_content_inbox_finalize.py`. Following
    that is what stops the join from reporting nine anchorless ids against a file that was
    never going to hold them.

    Restricted to lines that INVOKE python in command position, and never to a comment.
    Both halves of that were paid for. tests/test_fleet_guards.sh names its own path in a
    Python literal and tests/test_buzz_interactive_harness.sh names another suite's path in
    a prose cross-reference, so "any tests/… string" was never the rule. But "any line
    containing the word python" is not the rule either, and that version SHIPPED for about
    an hour: the header comment added to tests/test_content_inbox_finalize.sh by this same
    change says `asserts-anchored in tests/test_workflow_coverage.py follows the exec line`,
    which matched, and this checker's own source was silently joined into the finalize
    entry's scan set. It was harmless only because that file carries no anchors — the next
    file to mention a companion in prose would have had every anchor reported as undeclared,
    in an entry that never named it. Caught by the mutation test, not by reading.
    """
    files = [path]
    source = ROOT / path
    if source.is_file():
        for line in source.read_text().splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#") or not PY_INVOKE.search(stripped):
                continue
            for companion in COMPANION.findall(line):
                if companion != path and companion not in files \
                        and (ROOT / companion).is_file():
                    files.append(companion)
    return files


joined_ids = 0
joined_suites = 0
for path, declared in fleet_entries:
    # A missing or unnamed path is tests/test_fleet_guards.sh's finding to report; joining
    # against a file that is not there would restate it as a pile of absent anchors.
    if not path or not (ROOT / path).is_file():
        continue
    joined_suites += 1
    sources = suite_sources(path)
    anchored = {}
    for source in sources:
        for found in ANCHOR.findall((ROOT / source).read_text()):
            anchored.setdefault(found, source)
    joined_ids += len(anchored)
    where = " + ".join(sources)
    if declared and not anchored:
        problem("asserts-anchored",
                f"{path}: declares {len(declared)} assert id(s) and {where} carries no "
                "anchor at all — the join reached nothing, so it compared nothing")
        continue
    for want in declared:
        if want not in anchored:
            problem("asserts-anchored",
                    f"{path}: declares '{want}' and no assertion in {where} is anchored "
                    "to it — the id was renamed on one side only")
    for found, source in sorted(anchored.items()):
        if found not in declared:
            problem("asserts-anchored",
                    f"{path}: {source} anchors '{found}', which that entry's asserts list "
                    "in design/fleet-suites.toml does not declare")

# --- the unit side -------------------------------------------------------------------
declared_units = {w.get("unit") for _, w in entries}
missing_families = []
for timer in sorted(ROOT.glob("systemd/**/*.timer")):
    if "archive" in timer.relative_to(ROOT).parts:
        continue
    # A template family is one entry, not one per instance: praetorium-phaseb-brief@6 is an
    # instance of praetorium-phaseb-brief@, which is the join key to systemd.
    family = timer.stem
    if "@" in family:
        family = family.split("@", 1)[0] + "@"
    if family not in declared_units and family not in missing_families:
        missing_families.append(family)
        problem("timer-family-declared",
                f"{family}: a *.timer family in systemd/ that no [[workflows]] entry declares")

# --- report --------------------------------------------------------------------------
by_status = {}
for _, w in entries:
    by_status[w.get("status")] = by_status.get(w.get("status"), 0) + 1

print(f"  parsed {len(entries)} workflow entries from {len(manifests)} manifests: "
      + ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())))
print(f"  standing coverage: {len(covered)} of {len(standing)} own a suite, "
      f"{len(exempt)} exempt, {len(uncovered)} uncovered")
print(f"  {len(claimed)} distinct suite paths claimed "
      f"({len(fleet_owned)} by design/fleet-suites.toml); "
      f"{len(unclaimed)} of {len(suites)} suites unclaimed, {len(orphans)} orphaned")
# Printed on every run, not only on a finding. The `asserts` join's own failure mode is
# reaching nothing, and its assertion is a negative one — so the size of what it compared
# is the only thing on screen that distinguishes a clean pass from an empty one.
print(f"  asserts join: {joined_ids} anchored id(s) matched across {joined_suites} "
      f"declared suite(s)")

print("  exempt from needing a suite — named, never merely skipped:")
for unit, reason in exempt:
    print(f"EXEMPT\t{unit}\t{reason}")

print(f"SUMMARY\tentries={len(entries)} standing={len(standing)} covered={len(covered)} "
      f"exempt={len(exempt)} uncovered={len(uncovered)} unclaimed={len(unclaimed)} "
      f"orphans={len(orphans)}")
for assertion, detail in problems:
    print(f"PROBLEM\t{assertion}\t{detail}")
