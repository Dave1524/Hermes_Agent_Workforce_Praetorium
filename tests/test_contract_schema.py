#!/usr/bin/env python3
"""
Contract schema validator (T1.4). Driven from tests/test_contract_schema.sh.

    python3 tests/test_contract_schema.py [ROOT]

Reads ROOT/design/contracts/*.md against ROOT/design/agents/*.toml and prints a human
report plus one machine line per finding — the same protocol as tests/test_workflow_coverage.py:

    PROBLEM<TAB><rule-id><TAB><detail>
    EXEMPT<TAB><contract path><TAB><reason>
    SUMMARY<TAB>contracts=N declared=M absent=A exempt=E

Exit status is always 0 — the caller decides, so a run that finds eleven problems prints all
eleven instead of dying on the first.

THE JOIN IS DECLARED, NOT INFERRED. A contract's owners are the bold tokens in its Identity
Owner(s) row, and its units are the `.service`/`.timer` tokens in its Unit(s) row; the other
side is every [[workflows]] entry whose `contract` names the file. Both directions are
compared. Nothing is derived from the file name except rule 1 (named for the unit), which a
contract may opt out of by saying so in its preamble — printed as EXEMPT, never skipped.

WHAT IT DOES NOT REPORT. A manifest naming a contract that does not exist: that is T1.1's
rule in the coverage checker, which ships red on the ten missing files. Counted here as
`absent=` so the summary says what was skipped.
"""
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 \
    else pathlib.Path(__file__).resolve().parents[1]

SECTIONS = ["Identity", "Trigger", "Inputs", "Outputs", "Decline conditions",
            "Side effects", "Acceptance checks", "Known failure modes"]
BOLD = re.compile(r"\*\*([A-Za-z0-9_-]+)\*\*")
BRACES = re.compile(r"([A-Za-z0-9@._-]*)\{([^{}]+)\}([A-Za-z0-9@._-]*)")
TOKEN = re.compile(r"[A-Za-z0-9@._-]+")
UNIT_SUFFIX = re.compile(r"\.(service|timer)$")
RULE1_OPT_OUT = re.compile(r"breaks rule 1", re.I)

problems = []
exempt = []


def problem(rule, detail):
    problems.append((rule, detail))


# --- contract parsing -------------------------------------------------------------------
def parse_contract(text):
    """(preamble lines, [(heading, body lines)...]) split on `## ` headings.

    A heading inside a fenced code block is content, not a section: knowledge-digest.md
    fences its DECLINE sentinel and a future contract will fence a command whose output
    starts with `##`.
    """
    preamble, sections = [], []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            sections.append((line[3:].strip(), []))
            continue
        (sections[-1][1] if sections else preamble).append(line)
    return preamble, sections


def identity_row(body, *labels):
    """The second cell of the first table row whose first cell is one of `labels`."""
    for line in body:
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].strip("*` ").lower() in labels:
            return cells[1]
    return None


def units_in(cell):
    """Unit names in a Unit(s) cell: brace-expanded, `.service`/`.timer` stripped.

    `buzz-agent@{marcus,trajan}.service` yields two; a bare `.timer` after a slash yields
    the empty string and is dropped; `(--user scope)` yields nothing.
    """
    expanded = BRACES.sub(
        lambda m: " ".join(m.group(1) + alt.strip() + m.group(3)
                           for alt in m.group(2).split(",")), cell)
    found = set()
    for token in TOKEN.findall(expanded):
        if UNIT_SUFFIX.search(token):
            name = UNIT_SUFFIX.sub("", token)
            if name:
                found.add(name)
    return found


# --- the manifest side -------------------------------------------------------------------
declared = {}          # contract path -> [(manifest stem, unit)]
manifests = sorted((ROOT / "design" / "agents").glob("*.toml"))
for manifest in manifests:
    try:
        data = tomllib.loads(manifest.read_text())
    except tomllib.TOMLDecodeError as exc:
        problem("manifest-parse", f"{manifest.name}: does not parse: {exc}")
        continue
    for w in data.get("workflows", []):
        if w.get("contract"):
            declared.setdefault(w["contract"], []).append((manifest.stem, w.get("unit")))

by_unit = {}
for path, entries in declared.items():
    for stem, unit in entries:
        by_unit.setdefault(unit, {})[path] = stem
for unit, paths in sorted(by_unit.items()):
    if len(paths) > 1:
        problem("one-contract-per-unit",
                f"{unit}: named by {len(paths)} contracts — "
                + ", ".join(f"{p} ({s}.toml)" for p, s in sorted(paths.items())))

# --- the contract side -------------------------------------------------------------------
contracts = sorted((ROOT / "design" / "contracts").glob("*.md"))
for contract in contracts:
    rel = contract.relative_to(ROOT).as_posix()
    preamble, sections = parse_contract(contract.read_text())
    headings = [h for h, _ in sections]

    for want in SECTIONS:
        n = headings.count(want)
        if n == 0:
            problem("sections-present", f"{rel}: missing ## {want}")
        elif n > 1:
            problem("sections-present", f"{rel}: ## {want} appears {n} times")

    present = [h for h in dict.fromkeys(headings) if h in SECTIONS]
    expected = [s for s in SECTIONS if s in present]
    for got, want in zip(present, expected):
        if got != want:
            problem("sections-ordered",
                    f"{rel}: ## {got} is out of place — schema order puts ## {want} there")
            break

    for heading, body in sections:
        if heading in SECTIONS and not any(line.strip() for line in body):
            problem("sections-nonempty", f'{rel}: ## {heading} is empty — write "none"')

    entries = declared.get(rel, [])
    if not entries:
        problem("contract-declared",
                f"{rel}: named by no [[workflows]].contract in any manifest")
        continue
    owners = sorted({stem for stem, _ in entries})
    units = sorted({unit for _, unit in entries if unit})

    if "Identity" in headings:
        body = sections[headings.index("Identity")][1]
        owner_cell = identity_row(body, "owner", "owners")
        if owner_cell is None:
            problem("owner-matches-manifest", f"{rel}: no Owner/Owners row in ## Identity")
        else:
            named = sorted(set(BOLD.findall(owner_cell)))
            if named != owners:
                problem("owner-matches-manifest",
                        f"{rel}: Owner row names {', '.join(named) or 'nobody in bold'}; "
                        f"declared by {', '.join(owners)}")
        unit_cell = identity_row(body, "unit", "units")
        if unit_cell is None:
            problem("units-match-manifest", f"{rel}: no Unit/Units row in ## Identity")
        else:
            named = sorted(units_in(unit_cell))
            if named != units:
                problem("units-match-manifest",
                        f"{rel}: Unit row names {', '.join(named) or 'no unit'}; "
                        f"manifests declare {', '.join(units)}")

    if contract.stem not in units:
        if RULE1_OPT_OUT.search("\n".join(preamble)):
            exempt.append((rel, f"named for a surface, not a unit — its preamble says it "
                                f"breaks rule 1 ({len(units)} units)"))
        else:
            problem("named-for-unit",
                    f"{rel}: stem is none of its units ({', '.join(units)}) and the "
                    "preamble does not say it breaks rule 1")

# --- report ----------------------------------------------------------------------------
absent = sorted(p for p in declared if not (ROOT / p).is_file())
print(f"  validated {len(contracts)} contract(s) under design/contracts/ against "
      f"{len(manifests)} manifest(s); {len(declared)} distinct contract path(s) declared, "
      f"{len(absent)} absent (T1.1's rule, not reported here)")
print("  exempt from rule 1 (named for the unit) — named, never merely skipped:")
for rel, reason in exempt:
    print(f"EXEMPT\t{rel}\t{reason}")
print(f"SUMMARY\tcontracts={len(contracts)} declared={len(declared)} "
      f"absent={len(absent)} exempt={len(exempt)}")
for rule, detail in problems:
    print(f"PROBLEM\t{rule}\t{detail}")
