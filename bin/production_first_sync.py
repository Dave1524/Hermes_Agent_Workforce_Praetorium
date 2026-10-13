#!/usr/bin/env python3
"""Keep the production-first rule identical everywhere an agent session reads it.

docs/production-first.md holds the rule between two marker lines. `apply` writes that block into
each target instruction file (replacing a stale block, appending when there is none) and
`check` exits 1 naming every target that drifted, plus every plan or ship command file that
lacks the brief sections the rule asks for.

    render                          print the canonical block
    apply  [--create] [TARGET...]   write the block; --create makes a missing target
    check  [TARGET...]              exit 1 on a missing, unmarked or drifted target or command

Defaults are the two user-scope files for Claude Code and Codex, and ~/.claude/commands.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

START = "<!-- production-first:start -->"
END = "<!-- production-first:end -->"
RULE = pathlib.Path(__file__).resolve().parent.parent / "docs" / "production-first.md"
COMMAND_MUST_HAVE = {
    "plan-feature.md": ("## Design research", "## Decisions for Dave", "Production first"),
    "ship.md": ("Decisions for Dave", "Production first"),
}


def home_targets(home: pathlib.Path) -> list[pathlib.Path]:
    return [home / ".claude" / "CLAUDE.md", home / ".codex" / "AGENTS.md"]


def canonical(rule: pathlib.Path = RULE) -> str:
    text = rule.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise SystemExit(f"{rule}: expected exactly one {START} ... {END} pair")
    return text[text.index(START):text.index(END) + len(END)]


def has_block(text: str) -> bool:
    return text.count(START) == 1 and text.count(END) == 1 and text.index(START) < text.index(END)


def block_of(text: str) -> str:
    return text[text.index(START):text.index(END) + len(END)]


def with_block(text: str, block: str) -> str:
    if has_block(text):
        return text[:text.index(START)] + block + text[text.index(END) + len(END):]
    body = text.rstrip("\n")
    return f"{body}\n\n{block}\n" if body else f"{block}\n"


def apply(targets: list[pathlib.Path], create: bool, block: str) -> int:
    for target in targets:
        if not target.exists() and not create:
            print(f"missing: {target} (use --create)", file=sys.stderr)
            return 1
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        updated = with_block(current, block)
        if updated != current:
            target.write_text(updated, encoding="utf-8")
            print(f"updated: {target}")
        else:
            print(f"unchanged: {target}")
    return 0


def problems(targets: list[pathlib.Path], commands: pathlib.Path, block: str) -> list[str]:
    found = []
    for target in targets:
        if not target.exists():
            found.append(f"missing: {target}")
        elif not has_block(target.read_text(encoding="utf-8")):
            found.append(f"no marked block: {target}")
        elif block_of(target.read_text(encoding="utf-8")) != block:
            found.append(f"drifted from docs/production-first.md: {target}")
    for name, needles in COMMAND_MUST_HAVE.items():
        path = commands / name
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        found += [f"{path}: lacks {needle!r}" for needle in needles if needle not in text]
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("render")
    for name in ("apply", "check"):
        verb = sub.add_parser(name)
        verb.add_argument("targets", nargs="*", type=pathlib.Path)
        verb.add_argument("--home", type=pathlib.Path, default=pathlib.Path.home())
        verb.add_argument("--rule", type=pathlib.Path, default=RULE)
    sub.choices["apply"].add_argument("--create", action="store_true")
    args = parser.parse_args(argv)
    if args.verb == "render":
        print(canonical())
        return 0
    block = canonical(args.rule)
    targets = args.targets or home_targets(args.home)
    if args.verb == "apply":
        return apply(targets, args.create, block)
    found = problems(targets, args.home / ".claude" / "commands", block)
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
