#!/usr/bin/env bash
# Offline validation for project-local OpenCode agent configs.
# Does not invoke models or the network. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$REPO_ROOT/.opencode/agents"
PLANNER="$AGENTS_DIR/praetorium-planner.md"
DEVELOPER="$AGENTS_DIR/praetorium-developer.md"
QA="$AGENTS_DIR/praetorium-qa.md"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then
    echo "  ok: $desc"
  else
    echo "  FAIL: $desc"
    fail=1
  fi
}

# ── 1. Agent files exist ───────────────────────────────────────────────────────

echo "test: opencode-agents — files exist"
assert "planner agent file exists" "[[ -f '$PLANNER' ]]"
assert "developer agent file exists" "[[ -f '$DEVELOPER' ]]"
assert "qa agent file exists" "[[ -f '$QA' ]]"

# ── 2. Frontmatter structure ───────────────────────────────────────────────────

echo "test: opencode-agents — frontmatter structure"

python3 - "$PLANNER" "$DEVELOPER" "$QA" <<'PY'
import re
import sys
from pathlib import Path

fail = 0

def parse_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path.name}: missing opening frontmatter fence")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise AssertionError(f"{path.name}: missing closing frontmatter fence")
    fm = text[4:end]
    body = text[end + 5 :]
    data = {}
    current_list_key = None
    for raw in fm.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if re.match(r"^[A-Za-z0-9_]+:\s*$", line):
            key = line[:-1]
            data[key] = {}
            current_list_key = key
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.+)$", line)
        if m and not line.startswith(" "):
            data[m.group(1)] = m.group(2).strip().strip('"').strip("'")
            current_list_key = None
            continue
        m2 = re.match(r"^  ([A-Za-z0-9_*\"' .-]+):\s*(.+)$", line)
        if m2 and current_list_key:
            key = m2.group(1).strip().strip('"').strip("'")
            val = m2.group(2).strip().strip('"').strip("'")
            if not isinstance(data[current_list_key], dict):
                data[current_list_key] = {}
            data[current_list_key][key] = val
            continue
        m3 = re.match(r"^    ([A-Za-z0-9_*\"' .-]+):\s*(.+)$", line)
        if m3 and current_list_key:
            # nested map under permission.bash etc — flatten as "parent.child"
            parent = None
            # last top-level nested key under current_list_key that is a dict-ish
            if isinstance(data.get(current_list_key), dict):
                # attach under the most recent non-scalar parent if present
                pass
            key = m3.group(1).strip().strip('"').strip("'")
            val = m3.group(2).strip().strip('"').strip("'")
            # store nested bash rules as bash.<pattern>
            if "bash" in data.get(current_list_key, {}):
                # convert bash scalar into nested dict on first nested entry
                if not isinstance(data[current_list_key].get("bash"), dict):
                    data[current_list_key]["bash"] = {}
            # Prefer nesting under bash if previous key was bash
            # Heuristic: if indent is 4 spaces, attach to the last 2-space key that has no simple value
            # Simpler approach: store as f"{last_key}.{key}" if last_key exists
            # We'll re-parse with a stack below instead.
            pass
    # Re-parse with indent stack for nested maps
    data = {}
    stack = [(-1, data)]
    for raw in fm.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip().strip('"').strip("'")
        val = rest.strip().strip('"').strip("'")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if val == "":
            node = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = val
    return data, body

required_headings = {
    "praetorium-planner.md": [
        "## Plan",
        "## Files",
        "## Acceptance Tests",
        "## Risks",
        "## Blockers",
    ],
    "praetorium-developer.md": [
        "## Changed",
        "## Tests",
        "## Remaining",
        "## Needs Approval",
    ],
    "praetorium-qa.md": [
        "## Verdict: PASS|FAIL|BLOCKED",
        "## Findings",
        "## Tests Run",
        "## Security Checks",
    ],
}

for path_str in sys.argv[1:]:
    path = Path(path_str)
    try:
        data, body = parse_frontmatter(path)
    except Exception as e:
        print(f"  FAIL: {path.name}: frontmatter parse error: {e}")
        fail = 1
        continue

    ok = True
    for field in ("description", "mode", "permission"):
        if field not in data or data[field] in ("", None):
            print(f"  FAIL: {path.name}: missing frontmatter field '{field}'")
            ok = False
            fail = 1
    if "permission" in data and not isinstance(data["permission"], dict):
        print(f"  FAIL: {path.name}: permission must be a map")
        ok = False
        fail = 1
    if ok:
        print(f"  ok: {path.name} has description, mode, and permission rules")

    # Permission checks
    perms = data.get("permission", {}) if isinstance(data.get("permission"), dict) else {}
    name = path.name
    if name == "praetorium-planner.md":
        if perms.get("edit") != "deny":
            print(f"  FAIL: planner edit must be deny (got {perms.get('edit')!r})")
            fail = 1
        else:
            print("  ok: planner edit is denied")
        if perms.get("task") != "deny":
            print(f"  FAIL: planner task must be deny (got {perms.get('task')!r})")
            fail = 1
        else:
            print("  ok: planner task is denied")
    elif name == "praetorium-developer.md":
        if perms.get("edit") != "ask":
            print(f"  FAIL: developer edit must be ask/approval-controlled (got {perms.get('edit')!r})")
            fail = 1
        else:
            print("  ok: developer edit is approval-controlled (ask)")
        bash = perms.get("bash", {})
        if not isinstance(bash, dict):
            print(f"  FAIL: developer bash permissions must be a map (got {bash!r})")
            fail = 1
            bash = {}
        denied = {
            "git push*": bash.get("git push*"),
            "sudo *": bash.get("sudo *"),
            "systemctl *": bash.get("systemctl *"),
            "rm -rf *": bash.get("rm -rf *"),
        }
        for rule, val in denied.items():
            if val != "deny":
                print(f"  FAIL: developer must deny '{rule}' (got {val!r})")
                fail = 1
            else:
                print(f"  ok: developer denies '{rule}'")
        # destructive deletion: rm -f / rm -rf already; also ensure bare rm is not allow
        if bash.get("rm *") == "allow":
            print("  FAIL: developer must not allow unrestricted 'rm *'")
            fail = 1
        else:
            print("  ok: developer does not allow unrestricted 'rm *'")
        if perms.get("external_directory") != "deny":
            print(f"  FAIL: developer external_directory must be deny (got {perms.get('external_directory')!r})")
            fail = 1
        else:
            print("  ok: developer denies external_directory")
    elif name == "praetorium-qa.md":
        if perms.get("edit") != "deny":
            print(f"  FAIL: qa edit must be deny (got {perms.get('edit')!r})")
            fail = 1
        else:
            print("  ok: qa edit is denied")
        if perms.get("task") != "deny":
            print(f"  FAIL: qa task must be deny (got {perms.get('task')!r})")
            fail = 1
        else:
            print("  ok: qa task is denied")

    for heading in required_headings.get(name, []):
        if heading not in body:
            print(f"  FAIL: {name}: missing required output heading '{heading}'")
            fail = 1
        else:
            print(f"  ok: {name} includes '{heading}'")

sys.exit(fail)
PY
rc=$?
if [[ $rc -ne 0 ]]; then
  fail=1
fi

# ── 3. Capture directory is gitignored ─────────────────────────────────────────

echo "test: opencode-agents — capture dir gitignored"
assert "var/opencode-observability/ is gitignored" \
  "git -C '$REPO_ROOT' check-ignore -q var/opencode-observability/flows/sample.json"

# ── Summary ───────────────────────────────────────────────────────────────────

echo "---"
if [ "$fail" -eq 0 ]; then
  echo "  all opencode-agents tests passed"
else
  echo "  FAIL: some opencode-agents tests failed"
fi
exit $fail
