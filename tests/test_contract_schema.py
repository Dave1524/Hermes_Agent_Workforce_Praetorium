#!/usr/bin/env python3
"""
Contract schema validator (T1.4). Driven from tests/test_contract_schema.sh.

    python3 tests/test_contract_schema.py [ROOT]

Reads ROOT/design/contracts/*.md against ROOT/design/agents/*.toml and prints a human
report plus one machine line per finding — the same protocol as tests/test_workflow_coverage.py:

    PROBLEM<TAB><rule-id><TAB><detail>
    EXEMPT<TAB><contract path><TAB><reason>
    SUMMARY<TAB>contracts=N declared=M absent=A exempt=E sections=S

Exit status is always 0 — the caller decides, so a run that finds eleven problems prints all
eleven instead of dying on the first.

THE SECTION LIST IS READ, NOT RETYPED. design/contract-schema.md declares the eight sections
as ``### `## X` `` headings and this file parses them from there, so a rename lands in one
place instead of leaving the validator grading the old shape. Exactly eight is the vacuity
guard: a schema doc this could not read would otherwise grade every contract against an empty
section list and call the tree clean.

THE JOIN IS DECLARED, NOT INFERRED. A contract's owners are the bold tokens in its Identity
Owner(s) row, and its units are the `.service`/`.timer` tokens in its Unit(s) row; the other
side is every [[workflows]] entry whose `contract` names the file. Both directions are
compared. Nothing is derived from the file name except rule 1 (named for the unit), which a
contract opts out of with `rule1_exempt = "<reason>"` on a declaring [[workflows]] entry — the
same shape as `suite_exempt` in tests/test_workflow_coverage.py, and printed as EXEMPT, never
merely skipped. Until 2026-09-09 the opt-out was a case-insensitive search for the string
"breaks rule 1" anywhere in the contract's preamble. That is polarity-blind: a contract whose
preamble said the opposite — that buzz-interactive.md breaks rule 1 and this one does not —
exempted itself, and so did any file quoting the rule. A declaration cannot be read backwards.

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

SCHEMA_DOC = "design/contract-schema.md"
SCHEMA_HEADING = re.compile(r"^### `## (.+)`\s*$")
BOLD = re.compile(r"\*\*([A-Za-z0-9_-]+)\*\*")
# `%` is in both classes so `agent-alert@%n.service` stays ONE token and can be recognised as
# a systemd specifier. Split on `%` it became `agent-alert@` plus `n.service`, and the Unit
# row of any contract that mentioned its OnFailure line declared a phantom unit named `n`.
BRACES = re.compile(r"([A-Za-z0-9@._%-]*)\{([^{}]+)\}([A-Za-z0-9@._%-]*)")
TOKEN = re.compile(r"[A-Za-z0-9@._%-]+")
UNIT_SUFFIX = re.compile(r"\.(service|timer)$")
SUBHEADING = re.compile(r"^#{3,6} ")

problems = []
exempt = []


def problem(rule, detail):
    problems.append((rule, detail))


# --- the schema's own section list --------------------------------------------------------
def schema_sections():
    doc = ROOT / SCHEMA_DOC
    if not doc.is_file():
        problem("schema-sections",
                f"{SCHEMA_DOC}: absent — it declares the section list this validator grades "
                "against, so nothing below has a schema to be measured by")
        return []
    names = [m.group(1).strip()
             for m in (SCHEMA_HEADING.match(ln) for ln in doc.read_text().splitlines()) if m]
    if len(names) != 8:
        problem("schema-sections",
                f"{SCHEMA_DOC}: declares {len(names)} `### `## X`` section heading(s), "
                f"expected 8 ({', '.join(names) or 'none found'})")
    return names


SECTIONS = schema_sections()


# --- contract parsing -------------------------------------------------------------------
def parse_contract(text):
    """([(heading, body lines)...], line of an unclosed fence or None), split on `## `.

    A heading inside a fenced code block is content, not a section: knowledge-digest.md
    fences its DECLINE sentinel and a future contract will fence a command whose output
    starts with `##`. A fence that is never closed swallows every heading below it, which
    the section rules would report as six missing sections in a file that has them all.
    """
    sections = []
    opened = None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            opened = None if opened else n
        if opened is None and line.startswith("## "):
            sections.append((line[3:].strip(), []))
            continue
        if sections:
            sections[-1][1].append(line)
    return sections, opened


def cells_of(row):
    r"""The cells of a markdown table row.

    `\|` is a literal pipe and a pipe inside a `code span` is content. Splitting on every
    `|` shifted every later cell, so the second cell of a row carrying either was a
    fragment — and the red it produced named text the file did not contain.
    """
    cells, cur, code, i = [], [], False, 0
    while i < len(row):
        ch = row[i]
        if ch == "\\" and row[i + 1:i + 2] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur))
    while cells and not cells[0].strip():
        cells.pop(0)
    while cells and not cells[-1].strip():
        cells.pop()
    return [c.strip() for c in cells]


def identity_row(body, *labels):
    """The second cell of the first table row whose first cell is one of `labels`."""
    for line in body:
        if not line.lstrip().startswith("|"):
            continue
        cells = cells_of(line.strip())
        if len(cells) >= 2 and cells[0].strip("*` ").lower() in labels:
            return cells[1]
    return None


def units_in(cell):
    """Unit names in a Unit(s) cell: brace-expanded, `.service`/`.timer` stripped.

    `buzz-agent@{marcus,trajan}.service` yields two; a bare `.timer` after a slash yields
    the empty string and is dropped; `(--user scope)` yields nothing. A token carrying a
    systemd specifier (`agent-alert@%n.service`) is a template naming no unit and is
    dropped — a Unit row that names only such tokens declares no unit and goes red as one.
    """
    expanded = BRACES.sub(
        lambda m: " ".join(m.group(1) + alt.strip() + m.group(3)
                           for alt in m.group(2).split(",")), cell)
    found = set()
    for token in TOKEN.findall(expanded):
        if "%" in token or not UNIT_SUFFIX.search(token):
            continue
        name = UNIT_SUFFIX.sub("", token)
        if name:
            found.add(name)
    return found


def has_content(body):
    """Whether a section says anything.

    A sub-heading is a label and an empty fence is a hole; a section whose whole body is
    either says nothing while reading as full, which is the state `## X is empty — write
    "none"` exists to catch. Inside a fence every non-blank line counts, `###` included.
    """
    fenced = False
    for line in body:
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if not stripped:
            continue
        if not fenced and SUBHEADING.match(stripped):
            continue
        return True
    return False


# --- the manifest side -------------------------------------------------------------------
declared = {}          # contract path -> [{owner, unit, exempt}]
manifests = sorted((ROOT / "design" / "agents").glob("*.toml"))
for manifest in manifests:
    try:
        data = tomllib.loads(manifest.read_text())
    except tomllib.TOMLDecodeError as exc:
        problem("manifest-parse", f"{manifest.name}: does not parse: {exc}")
        continue
    for w in data.get("workflows", []):
        if not w.get("contract"):
            continue
        if not w.get("unit"):
            problem("entry-shape",
                    f"{manifest.name}: a [[workflows]] entry names contract "
                    f"{w['contract']} and no unit — the join has no left-hand side")
        declared.setdefault(w["contract"], []).append(
            {"owner": manifest.stem, "unit": w.get("unit"), "exempt": w.get("rule1_exempt")})

by_unit = {}
for path, entries in declared.items():
    for e in entries:
        if e["unit"]:
            by_unit.setdefault(e["unit"], {})[path] = e["owner"]
for unit, paths in sorted(by_unit.items()):
    if len(paths) > 1:
        problem("one-contract-per-unit",
                f"{unit}: named by {len(paths)} contracts — "
                + ", ".join(f"{p} ({s}.toml)" for p, s in sorted(paths.items())))

# --- the contract side -------------------------------------------------------------------
contracts = sorted((ROOT / "design" / "contracts").glob("*.md"))
for contract in contracts:
    rel = contract.relative_to(ROOT).as_posix()
    sections, open_fence = parse_contract(contract.read_text())
    if open_fence:
        problem("contract-parseable",
                f"{rel}: the code fence opened on line {open_fence} is never closed, so every "
                "`## ` heading below it was read as content — the section rules are skipped "
                "rather than run against a file that is not there")
        continue
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
        if heading in SECTIONS and not has_content(body):
            problem("sections-nonempty", f'{rel}: ## {heading} is empty — write "none"')

    entries = declared.get(rel, [])
    if not entries:
        problem("contract-declared",
                f"{rel}: named by no [[workflows]].contract in any manifest")
        continue
    owners = sorted({e["owner"] for e in entries})
    units = sorted({e["unit"] for e in entries if e["unit"]})

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
                        f"manifests declare {', '.join(units) or 'no unit'}")

    if contract.stem not in units:
        excusing = [e for e in entries if e["exempt"]]
        if excusing:
            reasons = sorted({str(e["exempt"]) for e in excusing})
            exempt.append((rel, f"{'; '.join(reasons)} — rule1_exempt on "
                                f"{len(excusing)} of {len(entries)} declaring entries"))
        else:
            problem("named-for-unit",
                    f"{rel}: stem is none of its units ({', '.join(units) or 'none'}) and no "
                    "declaring [[workflows]] entry carries rule1_exempt")

# --- report ----------------------------------------------------------------------------
absent = sorted(p for p in declared if not (ROOT / p).is_file())
print(f"  validated {len(contracts)} contract(s) under design/contracts/ against "
      f"{len(manifests)} manifest(s), on the {len(SECTIONS)} section(s) {SCHEMA_DOC} "
      f"declares; {len(declared)} distinct contract path(s) declared, "
      f"{len(absent)} absent (T1.1's rule, not reported here)")
print("  exempt from rule 1 (named for the unit) — named, never merely skipped:")
for rel, reason in exempt:
    print(f"EXEMPT\t{rel}\t{reason}")
print(f"SUMMARY\tcontracts={len(contracts)} declared={len(declared)} "
      f"absent={len(absent)} exempt={len(exempt)} sections={len(SECTIONS)}")
for rule, detail in problems:
    print(f"PROBLEM\t{rule}\t{detail}")
