#!/usr/bin/env python3
"""Mirror each pointer skill's `description` from its canonical vault skill — or check it.

A skill's level-1 surface is its `name` and `description` in the system prompt; that is the
only text the model sees when deciding whether to load it. The pointer tree carries the
description in *our* file, so if it paraphrases the vault's, the trigger text an agent reads
is never the one the vault wrote. This renders every `skills/<owner>/skills/<name>/SKILL.md`
as:

    ---
    name: <name>
    <the canonical frontmatter's `description` block, verbatim — folded YAML and quoting kept>
    ---
    <a fixed body naming the canonical directory>

The body stays a pointer; only the metadata the runtime reads from our file is mirrored.
`render` writes; `check` exits 1 with a diff when a committed pointer differs from what the
vault renders, 3 when the vault is not on this machine (the gate skips, not fails, off the box).
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import re
import sys

VAULT_SKILLS = pathlib.Path.home() / "vault" / "08_skills"
KEY_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:")

BODY = """
Canonical source: `08_skills/{name}/SKILL.md` in the vault; its bundled files sit beside it in
`08_skills/{name}/`. On this box: `~/vault/08_skills/{name}/`

This file is a pointer, never a copy. Read the canonical SKILL.md first and resolve its
relative references from that directory. The description above is the vault's, mirrored by
bin/pointer_skills_sync.py so the trigger text an agent reads is the one the vault wrote.
"""


def pointers(repo: pathlib.Path) -> list[pathlib.Path]:
    return sorted((repo / "skills").glob("*/skills/*/SKILL.md"))


def frontmatter_lines(text: str, where: pathlib.Path) -> list[str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise SystemExit(f"{where}: no YAML frontmatter")
    return lines[1:lines.index("---", 1)]


def frontmatter_block(lines: list[str], key: str, where: pathlib.Path) -> list[str]:
    """The raw lines of one top-level key: its own line plus every continuation line."""
    starts = [i for i, line in enumerate(lines) if line.startswith(f"{key}:")]
    if len(starts) != 1:
        raise SystemExit(f"{where}: expected one `{key}:` in the frontmatter, found {len(starts)}")
    end = next((i for i in range(starts[0] + 1, len(lines)) if KEY_LINE.match(lines[i])), len(lines))
    return lines[starts[0]:end]


def canonical_description(name: str, vault_skills: pathlib.Path) -> list[str]:
    canonical = vault_skills / name / "SKILL.md"
    if not canonical.is_file():
        raise SystemExit(f"{name}: no canonical skill at {canonical}")
    lines = frontmatter_lines(canonical.read_text(encoding="utf-8"), canonical)
    declared = frontmatter_block(lines, "name", canonical)[0].removeprefix("name:").strip()
    if declared != name:
        raise SystemExit(f"{name}: the canonical skill calls itself {declared!r}")
    return frontmatter_block(lines, "description", canonical)


def render_one(name: str, vault_skills: pathlib.Path) -> str:
    description = "\n".join(canonical_description(name, vault_skills))
    return f"---\nname: {name}\n{description}\n---\n{BODY.format(name=name)}"


def render(repo: pathlib.Path, vault_skills: pathlib.Path) -> dict[pathlib.Path, str]:
    return {path: render_one(path.parent.name, vault_skills) for path in pointers(repo)}


def write(repo: pathlib.Path, vault_skills: pathlib.Path) -> int:
    for path, text in render(repo, vault_skills).items():
        changed = path.read_text(encoding="utf-8") != text
        path.write_text(text, encoding="utf-8")
        print(f"{'rendered' if changed else 'unchanged'} {path.relative_to(repo)}")
    return 0


def check(repo: pathlib.Path, vault_skills: pathlib.Path) -> int:
    status = 0
    for path, expected in render(repo, vault_skills).items():
        actual = path.read_text(encoding="utf-8")
        if actual == expected:
            continue
        sys.stdout.writelines(difflib.unified_diff(actual.splitlines(True), expected.splitlines(True),
                                                   fromfile=str(path.relative_to(repo)), tofile="render"))
        status = 1
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "check"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[1]))
        command.add_argument("--vault-skills", default=str(VAULT_SKILLS))
    args = parser.parse_args(argv)
    vault_skills = pathlib.Path(args.vault_skills)
    if not vault_skills.is_dir():
        print(f"vault skills not present at {vault_skills} — nothing to render against", file=sys.stderr)
        return 3
    repo = pathlib.Path(args.repo)
    return write(repo, vault_skills) if args.command == "render" else check(repo, vault_skills)


if __name__ == "__main__":
    sys.exit(main())
