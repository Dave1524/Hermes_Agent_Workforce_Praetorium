#!/usr/bin/env python3
"""The Hermes residue rule (T6.1): every `hermes` line under bin/ systemd/ profiles/ is a
comment in a code file, a listed prose line, or one of the two pinned live dependencies.

A hit is any line containing `hermes`, case-insensitively, after the GitHub repository's own
name (Hermes_Agent_Workforce_Praetorium) is blanked out — the repo is named after the runtime
it no longer runs, and a rename is a separate decision from retiring the runtime. Code files
(.sh .py .service .timer .env.example .conf .toml .tsv, extension-less) pass a hit when the
line is a `#` comment or matches a `live` row; prose files (.md .json .txt) pass only via a
`historical` row. Paths with an `archive` component, `__pycache__` and `*.bak*` are skipped.

The live set is pinned here as a literal so a third live dependency cannot arrive unnamed:
the Discord delivery leg (bin/deliver.sh) retires with the Discord cutover, and
bin/local_tier_eval.sh with local-tier-eval itself.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hermes-residue"
ALLOWLIST = FIXTURES / "allowlist.tsv"
GATE_DIRS = ("bin", "systemd", "profiles")
PROSE_SUFFIXES = {".md", ".json", ".txt"}
SKIP_PARTS = {"archive", "__pycache__"}
REPO_NAME = "Hermes_Agent_Workforce_Praetorium"
HIT = re.compile("hermes", re.IGNORECASE)
COMMENT = re.compile(r"^\s*#")
LIVE_SET = {"bin/deliver.sh": "discord-cutover", "bin/local_tier_eval.sh": "local-tier-eval"}
PERSONA_PROFILE = re.compile(r"-p\s+(marcus|claudius|augustus|trajan)\b")


def is_skipped(rel: pathlib.Path) -> bool:
    return bool(SKIP_PARTS & set(rel.parts)) or ".bak" in rel.name


def is_prose(rel: pathlib.Path) -> bool:
    return rel.suffix in PROSE_SUFFIXES


def gate_files(root: pathlib.Path):
    for top in GATE_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root)
            if path.is_file() and not is_skipped(rel):
                yield rel


def hits(root: pathlib.Path):
    for rel in gate_files(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if HIT.search(line.replace(REPO_NAME, "")):
                yield rel.as_posix(), number, line


def read_allowlist(path: pathlib.Path):
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        cells = raw.split("\t")
        if len(cells) != 4:
            raise ValueError(f"{path.name}: expected 4 tab-separated cells, got {len(cells)}: {raw!r}")
        rows.append({"path": cells[0], "class": cells[1], "anchor": cells[2], "why": cells[3]})
    return rows


def row_excuses(row, rel: str, line: str, prose: bool) -> bool:
    wanted_class = "historical" if prose else "live"
    return row["path"] == rel and row["class"] == wanted_class and row["anchor"] in line


def scan(root: pathlib.Path, allowlist):
    findings, matched = [], set()
    for rel, number, line in hits(root):
        prose = is_prose(pathlib.Path(rel))
        excusing = [i for i, row in enumerate(allowlist) if row_excuses(row, rel, line, prose)]
        matched.update(excusing)
        if excusing or (not prose and COMMENT.match(line)):
            continue
        findings.append((rel, number, line.strip()))
    stale = [row for i, row in enumerate(allowlist) if i not in matched]
    return findings, stale


def render(findings):
    return "\n".join(f"  {rel}:{number}: {line}" for rel, number, line in findings)


class HermesResidue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allowlist = read_allowlist(ALLOWLIST)
        cls.findings, cls.stale = scan(ROOT, cls.allowlist)

    def test_code_line_is_comment_or_live(self):  # (::residue-code-line-is-comment-or-live)
        code = [f for f in self.findings if not is_prose(pathlib.Path(f[0]))]
        self.assertEqual(code, [], "\nlive hermes code lines that are neither a comment nor a pinned "
                         f"live row ({len(code)}):\n{render(code)}")

    def test_prose_is_listed(self):  # (::residue-prose-is-listed)
        prose = [f for f in self.findings if is_prose(pathlib.Path(f[0]))]
        self.assertEqual(prose, [], "\nprose hermes lines with no historical row "
                         f"({len(prose)}):\n{render(prose)}")

    def test_no_stale_row(self):  # (::residue-no-stale-row)
        self.assertEqual(self.stale, [], "\nallowlist rows that match no line — remove them:\n"
                         + "\n".join(f"  {r['path']}\t{r['class']}\t{r['anchor']}" for r in self.stale))

    def test_live_is_pinned(self):  # (::residue-live-is-pinned)
        live = {row["path"]: row["why"] for row in self.allowlist if row["class"] == "live"}
        self.assertEqual(live, LIVE_SET)
        for row in self.allowlist:
            self.assertIn(row["class"], {"historical", "live"}, row)
            if row["class"] == "historical":
                self.assertTrue(is_prose(pathlib.Path(row["path"])),
                                f"historical rows excuse prose only; a code line is a comment or live: {row}")

    def test_local_tier_on_base0(self):  # (::residue-local-tier-on-base0)
        text = (ROOT / "bin" / "local_tier_eval.sh").read_text(encoding="utf-8")
        self.assertTrue("-p base0" in text, "local_tier_eval.sh does not run -p base0")
        self.assertIsNone(PERSONA_PROFILE.search(text), "local_tier_eval.sh names a persona profile")

    def test_canary_red(self):  # (::residue-canary-red)
        red, red_stale = scan(FIXTURES / "tree-red", read_allowlist(FIXTURES / "tree-red" / "allowlist.tsv"))
        self.assertEqual([(f[0], f[1]) for f in red], [("bin/x.sh", 2)])
        self.assertEqual(red_stale, [])
        green, _ = scan(FIXTURES / "tree-green", read_allowlist(FIXTURES / "tree-green" / "allowlist.tsv"))
        self.assertEqual(green, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
