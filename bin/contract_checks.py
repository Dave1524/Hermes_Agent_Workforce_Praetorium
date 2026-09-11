#!/usr/bin/env python3
"""Contract parsing shared by the validator and the executor.

tests/test_contract_schema.py grades the ```check blocks of design/contracts/*.md;
bin/contract_exec.py runs them. Until 2026-09-11 (T5.1) the parser lived in the validator,
which reads ROOT from argv and runs at import, so nothing could import it — and bin/ is the
deployed tree while tests/ is not, so the executor may only import from here. Two parsers of
one syntax is the D6 class of defect this repo already names; this file is the one parser.

Pure functions. No argv, no I/O beyond the paths handed in. The vocabularies (the executor
environment, the vantages) are READ from design/contract-schema.md, never retyped, so the
validator's rules and the executor's exports cannot disagree about what a block may read.
"""
from __future__ import annotations

import pathlib
import re

SCHEMA_DOC = "design/contract-schema.md"
ENV_BLOCK = "#### Executor environment"
VANTAGE_BLOCK = "#### Vantage"
OUTPUTS_BLOCK = "#### Outputs fields"
ENV_BULLET = re.compile(r"^- `([A-Z][A-Z0-9_]*)`")
VANTAGE_BULLET = re.compile(r"^- `([a-z][a-z0-9-]*)`")
OUTPUTS_BULLET = re.compile(r"^- \*\*([A-Z][A-Za-z ]+)\*\*")

CHECKS_SECTION = "Acceptance checks"
OUTPUTS_SECTION = "Outputs"
ITEM = re.compile(r"^(\d+)\.\s")
CHECK_ID = re.compile(r"^[a-z][a-z0-9-]*$")
CHECK_ATTRS = ("id", "when")
DEFAULT_VANTAGE = "run"
# A sed or awk script is single-quoted, and its $p is not a shell read.
SINGLE_QUOTED = re.compile(r"'[^']*'")
VAR_READ = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")
VAR_SET = re.compile(r"(?:^\s*|[;&|(]\s*|\bfor\s+)([A-Za-z_][A-Za-z0-9_]*)(?:=|\s+in\b)")
LABELLED_BULLET = re.compile(r"^\s*[-*]\s+\*\*([^*]+?)\*\*:?\s*(.*)$")
NONE_WORDS = {"none", "none.", "n/a"}


# --- the schema doc's vocabularies ------------------------------------------------------
def schema_bullets(text: str, heading: str, bullet: re.Pattern) -> list[str]:
    """The bullets of one `#### ` block in the schema doc, until the next heading."""
    found, inside = [], False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.strip() == heading
            continue
        if inside:
            m = bullet.match(line)
            if m:
                found.append(m.group(1))
    return found


def executor_environment(doc: pathlib.Path) -> list[str]:
    """The variable names the executor exports — the schema's list, in the schema's order."""
    return schema_bullets(doc.read_text(), ENV_BLOCK, ENV_BULLET)


def vantages(doc: pathlib.Path) -> list[str]:
    return schema_bullets(doc.read_text(), VANTAGE_BLOCK, VANTAGE_BULLET)


# --- the check blocks -------------------------------------------------------------------
def acceptance_checks(text: str) -> tuple[list[int], list[dict]]:
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


def attrs_of(info: str) -> tuple[dict[str, str], list[str]]:
    """The info line's attributes after the leading `check`, and the tokens that are not."""
    good, bad = {}, []
    for token in info.split()[1:]:
        key, sep, value = token.partition("=")
        if sep and key in CHECK_ATTRS and key not in good:
            good[key] = value
        else:
            bad.append(token)
    return good, bad


def block_reads(body: list[str], env_vars) -> list[str]:
    """Variables the block reads without setting them earlier in the same block."""
    known, unknown = set(), []
    for line in body:
        line = SINGLE_QUOTED.sub("''", line)
        for var in VAR_READ.findall(line):
            if var not in known and var not in env_vars and var not in unknown:
                unknown.append(var)
        known.update(VAR_SET.findall(line))
    return unknown


def block_script(body: list[str]) -> str:
    """The block as the executor runs it: bash under `set -u`, never -e, never pipefail."""
    return "set -u\n" + "\n".join(body) + "\n"


# --- the outputs bullets ----------------------------------------------------------------
def outputs_bullets(text: str) -> dict[str, str]:
    """`{label: value}` for every `- **Label:** value` bullet of `## Outputs`, fence-aware.

    A continuation line (indented, not itself a bullet) is joined onto the value; a blank
    line ends it. Labels are lower-cased; values keep their words and lose their line breaks.
    """
    found: dict[str, str] = {}
    inside, fenced, label = False, False, None
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == OUTPUTS_SECTION
            label = None
            continue
        if not inside:
            continue
        if line.strip().startswith("```"):
            fenced = not fenced
            label = None
            continue
        if fenced:
            continue
        m = LABELLED_BULLET.match(line)
        if m:
            label = m.group(1).strip().rstrip(":").lower()
            found[label] = m.group(2).strip()
            continue
        if label and line.strip() and line[:1].isspace():
            found[label] = f"{found[label]} {line.strip()}".strip()
            continue
        label = None
    return found


def says_none(value: str | None) -> bool:
    return value is None or value.strip().strip("`").lower() in NONE_WORDS
