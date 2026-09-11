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
import json
import pathlib
import re
import sys
import tomllib

# An explicit root is how tests/test_workflow_coverage.sh points this at a mktemp fixture;
# every read below is is_file()-guarded, so a root carrying only design/agents/ and
# design/contracts/ runs to its report rather than to a traceback.
ROOT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 \
    else pathlib.Path(__file__).resolve().parents[1]
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


def peel(raw):
    raw = raw.strip().rstrip("\\").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return raw


def assignment_default(raw):
    raw = peel(raw)
    m = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]+)\}", raw)
    return m.group(1) if m else raw


def resolve_token(token, assigns):
    token = peel(token)
    m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", token)
    if m:
        name = m.group(1) or m.group(2)
        return assigns[name] if name in assigns else token
    m = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]+)\}", token)
    return m.group(1) if m else token


def uncommented_lines(path):
    """Left-stripped lines with blanks and comments dropped."""
    lines = []
    for line in path.read_text().splitlines():
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def shell_assigns(lines):
    """NAME=value assignments, ${VAR:-default} reduced to the default. One collector for
    the runner join and the skills join, so a runner's variables resolve identically in
    both — two loops would be one rule in two places."""
    assigns = {}
    for stripped in lines:
        am = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)", stripped)
        if am:
            assigns[am.group(1)] = assignment_default(am.group(2))
    return assigns


def mcp_servers_empty(raw):
    if not raw:
        return False
    text = peel(raw).replace('\\"', '"')
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return text.replace(" ", "") == '{"mcpServers":{}}'
    return obj.get("mcpServers") == {}


def runner_file(runner):
    if not isinstance(runner, str):
        return None
    for tok in re.split(r"(?:->)|[\s;|&]", runner):
        tok = tok.strip().strip("\"'")
        if tok and (ROOT / tok).is_file():
            return ROOT / tok
    return None


def parse_claude_flags(path):
    """Flags from uncommented lines. A comment naming --model is not the flag."""
    lines = uncommented_lines(path)
    assigns = shell_assigns(lines)
    model_tok, tools, strict, mcp_cfg = None, None, False, None
    for stripped in lines:
        if "--strict-mcp-config" in stripped:
            strict = True
        mm = re.search(r"--model\s+(\S+)", stripped)
        if mm:
            model_tok = mm.group(1)
        tm = re.search(r"--allowedTools\s+\"([^\"]+)\"", stripped)
        if tm:
            tools = [t.strip() for t in tm.group(1).split(",") if t.strip()]
        cm = re.search(r"--mcp-config\s+(\S.*)", stripped)
        if cm:
            mcp_cfg = cm.group(1)
    if model_tok is None and tools is None and not strict:
        return None
    return {
        "model": resolve_token(model_tok, assigns) if model_tok is not None else None,
        "tools": tools,
        "strict": strict,
        "mcp_empty": mcp_servers_empty(mcp_cfg),
    }


PLUGIN_DIR = re.compile(r"--plugin-dir\s+(\S+)")
# The runner names its tree in the DEPLOYED copy; the join reads the source it is deployed
# from, which bin/check_deploy_drift.sh holds equal.
DEPLOYED_PREFIXES = ("$HOME/agent-workforce/", "~/agent-workforce/")
VAULT_SKILL = re.compile(r"08_skills/([A-Za-z0-9_-]+)/SKILL\.md")
SKILLS_MECHANISMS = ("heading-extraction",)


def repo_path(raw):
    for prefix in DEPLOYED_PREFIXES:
        if raw.startswith(prefix):
            return ROOT / raw[len(prefix):]
    return pathlib.Path(raw)


def plugin_dir_tree(path):
    """The tree the runner's --plugin-dir DEFAULT resolves to; None when it passes none.

    Reads the declared default (${PRAETORIUM_SKILLS_DIR:-...}) exactly as the runner join
    reads --model — a runtime override is outside the manifest's jurisdiction.
    """
    if path is None:
        return None
    lines = uncommented_lines(path)
    assigns = shell_assigns(lines)
    tree = None
    for stripped in lines:
        pm = PLUGIN_DIR.search(stripped)
        if pm:
            tree = repo_path(resolve_token(pm.group(1), assigns))
    return tree


def pointer_names(tree):
    """Sorted skill dirs under <tree>/skills/ that carry a SKILL.md; [] for no tree. A
    directory without the manifest is not discovered by the runtime either."""
    if tree is None:
        return []
    return sorted(p.parent.name for p in tree.glob("skills/*/SKILL.md"))


def extracted_skills(profile_path):
    """Vault skills named as the target of each skill_sections.sh invocation. The path sits
    on a continuation line after the extractor token, so backslash-newlines are joined
    before each invocation is cut at its line end."""
    text = profile_path.read_text().replace("\\\n", " ")
    names = set()
    for invocation in text.split("skill_sections.sh")[1:]:
        names.update(VAULT_SKILL.findall(invocation.split("\n", 1)[0]))
    return sorted(names)


# --- parse ---------------------------------------------------------------------------
entries = []
scheduled_by_owner = {}
manifests = sorted((ROOT / "design" / "agents").glob("*.toml"))
for manifest in manifests:
    text = manifest.read_text()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        problem("parse-integrity", f"{manifest.name}: does not parse: {exc}")
        continue
    scheduled_by_owner[manifest.stem] = ((data.get("surfaces") or {}).get("scheduled") or {})
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

# --- contract-path join (T1.1, mandatory since T4.5) ----------------------------------
# Present and resolves. Every entry names a contract that is a file, or carries
# contract_exempt naming the reason — and the exemption is accepted only on a spent entry,
# because a promise nobody makes any more is the one thing that has nothing to contract.
# Neither field is red; both is red (an exemption claimed for a promise that is named is
# two owners of one fact). Two entries sharing one missing path produce one PROBLEM, not
# two — augustus-content is named twice.
contract_checked = 0
contract_declared = 0
contract_exempted = []
missing_contract_paths = []
seen_missing_contracts = set()
for owner, w in entries:
    contract_checked += 1
    unit = w.get("unit")
    path = w.get("contract")
    named = isinstance(path, str) and bool(path.strip())
    exempt_claimed = "contract_exempt" in w
    if not named and not exempt_claimed:
        problem("contract-declared",
                f"{unit} ({owner}): names no contract and claims no contract_exempt")
        continue
    if named and exempt_claimed:
        problem("contract-declared",
                f"{unit} ({owner}): names {path.strip()} and claims contract_exempt too")
        continue
    if exempt_claimed:
        reason = w["contract_exempt"]
        if not isinstance(reason, str) or not reason.strip():
            problem("contract-exempt-spent",
                    f"{unit} ({owner}): contract_exempt names no reason")
        elif w.get("status") != "spent":
            problem("contract-exempt-spent",
                    f"{unit} ({owner}): contract_exempt on a status = "
                    f"{w.get('status')!r} entry — only spent is exempt")
        else:
            contract_exempted.append((unit, reason.strip()))
        continue
    contract_declared += 1
    path = path.strip()
    if (ROOT / path).is_file():
        continue
    if path in seen_missing_contracts:
        continue
    seen_missing_contracts.add(path)
    missing_contract_paths.append(path)
    problem("contract-exists", path)

if entries and contract_checked < len(entries):
    problem("contract-join-counted",
            f"checked {contract_checked} of {len(entries)} entries — the join skipped some")

# --- standing reconciliation (T4.5) ---------------------------------------------------
# 31 entries are 30 workflows: a logical_workflow field folds a second trigger into the
# entry it triggers (content-change-dispatch -> augustus-content). The fold is declared,
# never inferred, so the only unexplained duplicate left is a unit name declared twice —
# and a fold is honest only if its key is a declared unit and every trigger of one
# workflow names one contract.
unit_counts = {}
for _, w in entries:
    unit_counts[w.get("unit")] = unit_counts.get(w.get("unit"), 0) + 1
for unit, n in sorted(unit_counts.items(), key=lambda item: str(item[0])):
    if n > 1:
        problem("logical-workflow-reconciled",
                f"{unit}: declared by {n} entries — a duplicate no field explains")

standing_units = {w.get("unit") for _, w in standing}
logical_groups = {}
for owner, w in standing:
    key = w.get("logical_workflow") or w.get("unit")
    if key not in standing_units:
        problem("logical-workflow-reconciled",
                f"{w.get('unit')} ({owner}): logical_workflow = {key!r} names no "
                "standing entry")
    logical_groups.setdefault(key, []).append(w)

second_triggers = []
for key, members in sorted(logical_groups.items(), key=lambda item: str(item[0])):
    contracts = {str(m.get("contract", "")).strip() for m in members}
    if len(members) > 1 and len(contracts) > 1:
        problem("logical-workflow-reconciled",
                f"{key}: its {len(members)} triggers name {len(contracts)} contracts "
                f"({', '.join(sorted(contracts))}) — one workflow, one contract")
    second_triggers += [(m.get("unit"), key) for m in members if m.get("unit") != key]

# --- runner join (T1.2) ----------------------------------------------------------------
# surfaces.scheduled tools / tools_web / mcp and each workflow's model against the named
# runner's --allowedTools / --strict-mcp-config / --model, read from the script. A missing
# runner, a non-file, or a script that does not pass those flags is counted and is not a
# PROBLEM. Honour web = true by adding tools_web — standing research's unit is
# agent-proposal, so a hardcoded unit list would miss it. Resolve ${VAR:-default}; never
# read a deny-listed env. Two entries sharing one runner are two findings.
runner_checked = 0
model_alias = []
for owner, w in entries:
    runner_checked += 1
    path = runner_file(w.get("runner"))
    if path is None:
        continue
    flags = parse_claude_flags(path)
    if flags is None:
        continue
    unit = w.get("unit")
    surf = scheduled_by_owner.get(owner) or {}
    declared_model = w.get("model")
    if isinstance(declared_model, str) and declared_model.strip() \
            and flags["model"] is not None \
            and flags["model"] != declared_model.strip():
        problem("model-alias", unit)
        model_alias.append(unit)
    want = set(surf.get("tools") or [])
    if w.get("web") is True:
        want.update(surf.get("tools_web") or [])
    got = set(flags["tools"] or [])
    if got != want:
        problem("runner-tools",
                f"{unit} ({owner}): allowlist {sorted(got)} != {sorted(want)}")
    declared_mcp = surf.get("mcp")
    if not isinstance(declared_mcp, list):
        declared_mcp = []
    empty_ok = flags["strict"] and flags["mcp_empty"]
    if declared_mcp == []:
        if not empty_ok:
            problem("runner-mcp",
                    f"{unit} ({owner}): scheduled mcp is empty, runner is not")
    elif flags["mcp_empty"]:
        problem("runner-mcp",
                f"{unit} ({owner}): scheduled mcp names {declared_mcp}, runner empties it")

if entries and runner_checked < len(entries):
    problem("runner-join-counted",
            f"checked {runner_checked} of {len(entries)} entries — the join skipped some")

# --- skills join (T3.2) ----------------------------------------------------------------
# `skills` on every entry is what the entry's mechanism DELIVERS to the run — not what the
# job might read, not what the profile mentions — joined by equality to an offer derived
# here. Default mechanism: the pointer names under the tree the runner's --plugin-dir
# resolves to; no runner or no flag is an offer of [], and [] must then be declared.
# `skills_mechanism = "heading-extraction"`: the vault skills the profile's
# skill_sections.sh invocations extract, each of which must be a pointer in the owner's
# tree. A missing field is a PROBLEM, never a default, and the join counts what it checked
# in three figures so the heading-extraction branch is proven exercised, not merely present.


def heading_extraction_offer(owner, w):
    unit, profile = w.get("unit"), w.get("profile")
    path = ROOT / profile if isinstance(profile, str) and profile.strip() else None
    if path is None or not path.is_file():
        problem("skills-mechanism",
                f"{unit} ({owner}): heading-extraction names no profile in this repo "
                f"({profile!r})")
        return []
    names = extracted_skills(path)
    if not names:
        problem("skills-mechanism",
                f"{unit} ({owner}): {profile} invokes skill_sections.sh on no vault skill")
        return []
    for name in names:
        if not (ROOT / "skills" / owner / "skills" / name / "SKILL.md").is_file():
            problem("skills-mechanism",
                    f"{unit} ({owner}): extracts {name}, which is not "
                    f"skills/{owner}/skills/{name}/SKILL.md")
    return names


def skills_offer(owner, w):
    mechanism = w.get("skills_mechanism")
    if mechanism is None:
        return pointer_names(plugin_dir_tree(runner_file(w.get("runner"))))
    if mechanism == "heading-extraction":
        return heading_extraction_offer(owner, w)
    problem("skills-mechanism",
            f"{w.get('unit')} ({owner}): skills_mechanism {mechanism!r} is not one of "
            f"{list(SKILLS_MECHANISMS)}")
    return []


skills_checked, skills_he, skills_offered = 0, 0, 0
for owner, w in entries:
    skills_checked += 1
    unit = w.get("unit")
    if w.get("skills_mechanism") == "heading-extraction":
        skills_he += 1
    offered = skills_offer(owner, w)
    if offered:
        skills_offered += 1
    declared = w.get("skills")
    if not isinstance(declared, list) or not all(isinstance(n, str) for n in declared):
        problem("skills-declared",
                f"{unit} ({owner}): skills is {declared!r}, not a list of strings — a "
                "missing field is not an empty offer")
        continue
    if len(set(declared)) != len(declared):
        problem("skills-declared", f"{unit} ({owner}): skills repeats a name: {declared}")
    if sorted(declared) != offered:
        problem("skills-join",
                f"{unit} ({owner}): declared {sorted(declared)} != offered {offered}")

if entries and skills_checked < len(entries):
    problem("skills-join-counted",
            f"checked {skills_checked} of {len(entries)} entries — the join skipped some")

# design/fleet-suites.toml's own SCHEMA is asserted by tests/test_fleet_guards.sh (path)
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
print(f"  contract join: checked {contract_checked} of {len(entries)} entries, "
      f"{contract_declared} declared, {len(contract_exempted)} exempt (spent), "
      f"{len(missing_contract_paths)} missing file(s)")
print(f"  standing reconciliation: {len(standing)} entries -> {len(logical_groups)} "
      f"logical workflow(s); {len(second_triggers)} second trigger(s)")
print(f"  runner join: checked {runner_checked} of {len(entries)} entries, "
      f"{len(model_alias)} model-alias(es)")
print(f"  skills join: checked {skills_checked} of {len(entries)} entries, "
      f"{skills_he} heading-extraction, {skills_offered} with a non-empty offer")

print("  exempt from needing a suite — named, never merely skipped:")
for unit, reason in exempt:
    print(f"EXEMPT\t{unit}\t{reason}")
print("  exempt from naming a contract — spent, and named, never merely skipped:")
for unit, reason in contract_exempted:
    print(f"CONTRACT_EXEMPT\t{unit}\t{reason}")
print("  second triggers folded into the workflow they trigger:")
for unit, key in second_triggers:
    print(f"SECOND_TRIGGER\t{unit}\t{key}")

print(f"SUMMARY\tentries={len(entries)} standing={len(standing)} covered={len(covered)} "
      f"exempt={len(exempt)} uncovered={len(uncovered)} unclaimed={len(unclaimed)} "
      f"orphans={len(orphans)} contract_checked={contract_checked} "
      f"contract_declared={contract_declared} contract_exempt={len(contract_exempted)} "
      f"contract_missing={len(missing_contract_paths)} "
      f"standing_logical={len(logical_groups)} runner_checked={runner_checked} "
      f"model_alias={len(model_alias)} skills_checked={skills_checked} "
      f"skills_he={skills_he} skills_offered={skills_offered}")
for assertion, detail in problems:
    print(f"PROBLEM\t{assertion}\t{detail}")
