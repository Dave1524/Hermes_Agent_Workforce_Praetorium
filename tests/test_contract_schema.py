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
import subprocess
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

# T4.0. The check syntax, and the two vocabularies it grades against — both READ from the
# schema doc's `#### ` blocks, never retyped here, for the same reason the section list is.
ENV_BLOCK = "#### Executor environment"
VANTAGE_BLOCK = "#### Vantage"
ENV_BULLET = re.compile(r"^- `([A-Z][A-Z0-9_]*)`")
VANTAGE_BULLET = re.compile(r"^- `([a-z][a-z0-9-]*)`")
CHECKS_SECTION = "Acceptance checks"
ITEM = re.compile(r"^(\d+)\.\s")
CHECK_ID = re.compile(r"^[a-z][a-z0-9-]*$")
CHECK_ATTRS = ("id", "when")
# A block whose every command is one of these decides nothing. The schema's own rule: a check
# that cannot fail is not a check.
TRIVIAL = re.compile(r"^(true|:|exit\s+0|echo(\s.*)?)$")
# A sed or awk script is single-quoted, and its $p is not a shell read.
SINGLE_QUOTED = re.compile(r"'[^']*'")
VAR_READ = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")
VAR_SET = re.compile(r"(?:^\s*|[;&|(]\s*|\bfor\s+)([A-Za-z_][A-Za-z0-9_]*)(?:=|\s+in\b)")

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


def schema_bullets(heading, bullet):
    """The bullets of one `#### ` block in the schema doc, until the next heading."""
    doc = ROOT / SCHEMA_DOC
    if not doc.is_file():
        return []
    found, inside = [], False
    for line in doc.read_text().splitlines():
        if line.startswith("#"):
            inside = line.strip() == heading
            continue
        if inside:
            m = bullet.match(line)
            if m:
                found.append(m.group(1))
    return found


def check_vocabulary():
    """The executor environment and the vantages, or a finding if either is missing.

    This is the vacuity guard for the five rules below, and it is the whole reason they can
    be trusted: a schema doc these could not be read from would leave every block graded
    against an empty vocabulary — no variable undeclared, no vantage wrong — and the tree
    would read clean.
    """
    if not (ROOT / SCHEMA_DOC).is_file():
        return set(), set()          # schema-sections already named the absent doc
    env = schema_bullets(ENV_BLOCK, ENV_BULLET)
    vantages = schema_bullets(VANTAGE_BLOCK, VANTAGE_BULLET)
    if not env:
        problem("checks-vocabulary",
                f"{SCHEMA_DOC}: declares no executor environment — no `{ENV_BLOCK}` block with "
                "`VAR` bullets, so every check block would be graded against an empty "
                "vocabulary and no variable could be undeclared")
    if not vantages:
        problem("checks-vocabulary",
                f"{SCHEMA_DOC}: declares no vantages — no `{VANTAGE_BLOCK}` block with "
                "`name` bullets, so no `when=` could be wrong")
    return set(env), set(vantages)


ENV_VARS, VANTAGES = check_vocabulary()


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
        if line.lstrip().startswith("```"):
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


def acceptance_checks(text):
    """([item numbers], [check blocks]) under `## Acceptance checks`, with real line numbers.

    A block belongs to the item it is indented under; one at column 0 has closed the list and
    belongs to nobody, which is a finding rather than something to adopt into the item above.
    """
    items, blocks = [], []
    inside, item, fence = False, None, None
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith("```"):
                if fence["info"].split(" ")[0] == "check" and fence["inside"]:
                    blocks.append(fence)
                fence = None
            else:
                fence["body"].append(line)
            continue
        if stripped.startswith("```"):
            fence = {"line": n, "indent": len(line) - len(line.lstrip()), "item": item,
                     "info": stripped[3:].strip(), "body": [], "inside": inside}
            continue
        if line.startswith("## "):
            inside = line[3:].strip() == CHECKS_SECTION
            item = None
            continue
        if inside:
            m = ITEM.match(line)
            if m:
                item = int(m.group(1))
                items.append(item)
    return items, blocks


def attrs_of(info):
    """The info line's attributes after the leading `check`, and the tokens that are not."""
    good, bad = {}, []
    for token in info.split()[1:]:
        key, sep, value = token.partition("=")
        if sep and key in CHECK_ATTRS and key not in good:
            good[key] = value
        else:
            bad.append(token)
    return good, bad


def block_reads(body):
    """Variables the block reads without setting them earlier in the same block."""
    known, unknown = set(), []
    for line in body:
        line = SINGLE_QUOTED.sub("''", line)
        for var in VAR_READ.findall(line):
            if var not in known and var not in ENV_VARS and var not in unknown:
                unknown.append(var)
        known.update(VAR_SET.findall(line))
    return unknown


def grade_checks(rel, text):
    """The T4.0 rules over one contract. Returns the number of blocks graded."""
    items, blocks = acceptance_checks(text)
    by_item = {}
    for block in blocks:
        if block["indent"] and block["item"] is not None:
            by_item.setdefault(block["item"], []).append(block)
        else:
            problem("checks-executable",
                    f"{rel}: the check block on line {block['line']} sits outside any numbered "
                    "item — indent it under the item it decides, or the list ends above it")
    if not items:
        problem("checks-executable",
                f"{rel}: ## {CHECKS_SECTION} carries no numbered check")
    for n in items:
        got = by_item.get(n, [])
        if not got:
            problem("checks-executable",
                    f"{rel}: check {n} carries no check block — a command named in prose is "
                    "not a command the executor can run")
        elif len(got) > 1:
            problem("checks-executable",
                    f"{rel}: check {n} carries {len(got)} check blocks — one item, one block, "
                    "so one result per check")

    seen = {}
    graded = 0
    for n in sorted(by_item):
        for block in by_item[n]:
            graded += 1
            good, bad = attrs_of(block["info"])
            ident = good.get("id")
            label = f"check {n} (id={ident})" if ident else f"check {n}"
            if ident is None:
                problem("checks-declared",
                        f"{rel}: check {n} declares no id= — a receipt and the scorecard have "
                        "nothing to call it, and a renumbered list would rename it")
            elif not CHECK_ID.match(ident):
                problem("checks-declared",
                        f"{rel}: {label}: an id is [a-z][a-z0-9-]*")
            elif ident in seen:
                problem("checks-declared",
                        f"{rel}: {label}: already used by check {seen[ident]}")
            else:
                seen[ident] = n
            if "when" in good and VANTAGES and good["when"] not in VANTAGES:
                problem("checks-declared",
                        f"{rel}: {label}: when={good['when']} is not a declared vantage "
                        f"({', '.join(sorted(VANTAGES))})")
            for token in bad:
                problem("checks-declared",
                        f"{rel}: {label}: unknown attribute {token} — the info line takes "
                        f"{' and '.join(a + '=' for a in CHECK_ATTRS)}")

            commands = [ln.strip() for ln in block["body"]
                        if ln.strip() and not ln.strip().startswith("#")]
            if not commands:
                problem("checks-decidable", f"{rel}: {label}: the block is empty")
            elif all(TRIVIAL.match(c) for c in commands):
                problem("checks-decidable",
                        f"{rel}: {label}: the block cannot fail — {commands[0]!r} decides "
                        "nothing, and a check that cannot fail is not a check")
            else:
                syntax = subprocess.run(["bash", "-n"], input="\n".join(block["body"]),
                                        capture_output=True, text=True)
                if syntax.returncode:
                    detail = (syntax.stderr.strip().splitlines() or ["no message"])[-1]
                    problem("checks-syntax",
                            f"{rel}: {label}: bash -n rejects the block: {detail}")

            if ENV_VARS:
                for var in block_reads(block["body"]):
                    problem("checks-env",
                            f"{rel}: {label}: reads ${var}, which the executor does not export "
                            "and the block does not set")
    return graded


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
            {"owner": manifest.stem, "unit": w.get("unit"), "exempt": w.get("rule1_exempt"),
             "kind": w.get("kind")})

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
graded = 0
for contract in contracts:
    rel = contract.relative_to(ROOT).as_posix()
    text = contract.read_text()
    sections, open_fence = parse_contract(text)
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
    units_named = sorted({e["unit"] for e in entries if e["unit"]})
    if entries and all(e["kind"] == "service" for e in entries):
        exempt.append((rel, "every declaring entry is kind = \"service\" ("
                            + ", ".join(f"{u}.service" for u in units_named)
                            + ") — an always-on unit has no run for the executor to decide a "
                              "check from: no RUN_DATE, no attempt log, no LastTriggerUSec"))
    else:
        graded += grade_checks(rel, text)

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
      f"absent={len(absent)} exempt={len(exempt)} sections={len(SECTIONS)} "
      f"checks={graded} env={len(ENV_VARS)}")
for rule, detail in problems:
    print(f"PROBLEM\t{rule}\t{detail}")
