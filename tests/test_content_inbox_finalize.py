#!/usr/bin/env python3
"""
Offline behaviour test for bin/content_inbox_finalize.py. Driven from
tests/test_content_inbox_finalize.sh so bin/verify.sh picks it up.

No network and no shell: `nr.api` is replaced by FakeNotion, `load_token` is stubbed so
the real secrets file is never read, and `subprocess.run` is replaced by FakeShell so
neither `notion_rest.py board` nor `systemctl show` nor `notify.sh` actually runs.

This tool runs once, unattended, at 22:00 on a board holding Dave's content, and it is
the last thing that will ever touch that board. So what is pinned here is not the happy
path — it is every way the run could do damage nobody would see until Monday:

  * A guard that fails must stop the pass with Notion untouched. Not warn, not continue.
  * A guard that cannot answer counts as failed. `nr.api` reports an HTTP error by
    calling sys.exit, so a bare `except Exception` would let a Notion blip through as an
    unhandled SystemExit and skip the refusal report entirely.
  * The freeze note must be inserted `after` the database block, not appended. Step 5
    trashes the database in the same pass; a note left inside it is visible to nobody.
  * The receipt must exist before the archive is attempted. A freeze that landed with no
    receipt is a change `undo` cannot find.
"""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "content_inbox_finalize", ROOT / "bin" / "content_inbox_finalize.py")
fin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fin)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


BASELINE = fin.INBOX_ROW_BASELINE
DB_TITLE = [{"plain_text": "Agent Content Inbox", "type": "text",
             "text": {"content": "Agent Content Inbox"}}]


class FakeNotion:
    """The slice of the Notion REST surface this tool touches."""

    def __init__(self, migrated=None, inbox_rows=BASELINE, fail_on=None,
                 archive_sticks=True):
        self.migrated = migrated if migrated is not None else {
            "new-{}".format(i): {"parent": {"data_source_id": fin.nr.DATA_SOURCE_ID}}
            for i in range(BASELINE)}
        self.inbox_rows = inbox_rows
        self.calls = []
        self.in_trash = False
        self.title = list(DB_TITLE)
        self.description = []
        self.deleted_blocks = []
        self._fail_on = fail_on or ()
        self._archive_sticks = archive_sticks

    def __call__(self, method, path, token, payload=None, timeout=30):
        self.calls.append((method, path, payload))
        for pattern in self._fail_on:
            if pattern in "{} {}".format(method, path):
                raise SystemExit("Notion API 502 on {} {}: simulated".format(method, path))
        head = path.split("?")[0].split("/")
        if method == "POST" and head[1] == "data_sources":
            return {"results": [{"id": "old-%d" % i} for i in range(self.inbox_rows)],
                    "has_more": False}
        if method == "GET" and head[1] == "pages":
            page = self.migrated.get(head[2])
            if page is None:
                raise SystemExit("Notion API 404 on GET /pages/{}".format(head[2]))
            return page
        if method == "GET" and head[1] == "databases":
            return {"title": self.title, "description": self.description,
                    "in_trash": self.in_trash}
        if method == "PATCH" and head[1] == "databases":
            if "in_trash" in payload:
                self.in_trash = payload["in_trash"] and self._archive_sticks
            if "title" in payload:
                self.title = payload["title"]
            if "description" in payload:
                self.description = payload["description"]
            return {"id": head[2]}
        if method == "PATCH" and head[1] == "blocks":
            return {"results": [{"id": "callout-1"}]}
        if method == "DELETE" and head[1] == "blocks":
            self.deleted_blocks.append(head[2])
            return {"id": head[2]}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def writes(self):
        return [c for c in self.calls if c[0] in ("PATCH", "DELETE", "POST")
                and not c[1].startswith("/data_sources/")]


class Completed:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


class FakeShell:
    """`notion_rest.py board`, `systemctl show` and `notify.sh`, without a shell."""

    def __init__(self, board_rows=BASELINE, board_rc=0, unit_status="0", unit_age_h=10.0):
        self.board_rows = board_rows
        self.board_rc = board_rc
        self.unit_status = unit_status
        self.unit_age_h = unit_age_h
        self.notifications = []

    def __call__(self, argv, capture_output=False, text=False, check=False, timeout=None):
        if argv[0] == "systemctl":
            return Completed(stdout=self._systemctl(argv[-1]))
        if argv[-1] == "0" and "board" in argv:
            if self.board_rc:
                return Completed(returncode=self.board_rc)
            return Completed(stdout=json.dumps([{"id": "r%d" % i}
                                                for i in range(self.board_rows)]))
        if argv[0] == fin.NOTIFY:
            self.notifications.append((argv[1], argv[2]))
            return Completed()
        raise AssertionError("unexpected subprocess: {}".format(argv))

    def _systemctl(self, prop):
        exit_at = fin.utcnow().timestamp() - self.unit_age_h * 3600
        values = {"ExecMainStatus": self.unit_status,
                  "ExecMainExitTimestamp": "@{}".format(int(exit_at))}
        # A real `systemctl show` prints in systemd's own order and may carry lines the
        # caller never asked for. Parsing anything but KEY=VALUE reads the wrong field.
        lines = ["Id=augustus-content.service"]
        if prop in values:
            lines.append("{}={}".format(prop, values[prop]))
        return "\n".join(lines) + "\n"


def workspace(live_files=None, ledger_entries=BASELINE):
    """A temp deployed tree: two ledgers, and the files the reference guard scans."""
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "var").mkdir()
    (root / "bin").mkdir()
    entries = [{"source": "old-%d" % i, "created": "new-%d" % i}
               for i in range(ledger_entries)]
    split = len(entries) - 1 if entries else 0
    for name, chunk in (("notion_content_migration.json", entries[:split]),
                        ("notion_content_migration_probe.json", entries[split:])):
        (root / "var" / name).write_text(json.dumps({"entries": chunk}))
    files = {
        "notion_rest.py": "DATA_SOURCE_ID = 'df18d768'\n",
        # Three files legitimately name the old data source once deployed: the rollback
        # tool, this tool itself, and a dated .bak of a retired profile. Only a fourth
        # hit is a finding.
        "augustus_content_task.md.bak-notion-rest-20260713-093716":
            "use {}\n".format(fin.INBOX_DATA_SOURCE),
    }
    for operator in fin.OPERATORS:
        files[operator] = "SOURCE_DS = '{}'\n".format(fin.INBOX_DATA_SOURCE)
    files.update(live_files or {})
    for name, body in files.items():
        (root / "bin" / name).write_text(body)
    fin.LEDGERS = [str(root / "var" / "notion_content_migration.json"),
                   str(root / "var" / "notion_content_migration_probe.json")]
    fin.LIVE_CODE_DIRS = [str(root / "bin")]
    fin.RECEIPT = str(root / "var" / "content_inbox_finalize.json")
    return root


def run(argv, api, shell):
    out, err = io.StringIO(), io.StringIO()
    raised, result = None, None
    fin.nr.api = api
    fin.nr.load_token = lambda: "test-token"
    fin.subprocess.run = shell
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = fin.main(argv)
    except BaseException as exc:  # noqa: BLE001 — the point is that nothing escapes untyped
        raised = exc
    return raised, result, out.getvalue(), err.getvalue()


print("--- check: all guards pass, and it writes nothing ---")
workspace()
api, shell = FakeNotion(), FakeShell()
raised, result, out, err = run(["check"], api, shell)
check("exits clean", raised is None and result == 0)
check("all six guards ran", out.count("PASS ") == 6)
check("it says so", "6/6 guards passed" in out)
check("nothing was written to Notion", api.writes() == [])

print("--- apply: freeze, then archive, then a receipt that can reverse both ---")
root = workspace()
api, shell = FakeNotion(), FakeShell()
raised, result, out, err = run(["apply", "--notify"], api, shell)
check("exits clean", raised is None and result == 0)
patched = [c for c in api.calls if c[0] == "PATCH" and c[1].startswith("/databases/")]
check("the database is renamed and described",
      set(patched[0][2]) == {"title", "description"})
check("the new title keeps the old one and marks it frozen",
      "Agent Content Inbox" in patched[0][2]["title"][0]["text"]["content"]
      and "frozen" in patched[0][2]["title"][0]["text"]["content"])
check("then it is archived", patched[1][2] == {"in_trash": True})
appended = [c for c in api.calls if c[0] == "PATCH" and c[1].startswith("/blocks/")][0]
check("the note goes on the PAGE, not inside the database",
      appended[1] == "/blocks/{}/children".format(fin.INBOX_PAGE))
# Appending would put the note below whatever else is on the page; `after` pins it to the
# slot the database occupies, so it takes that slot once the database is gone.
check("it is inserted after the database block, not appended",
      appended[2]["after"] == fin.INBOX_DATABASE)
check("the note says where the content went", "Content DB" in
      appended[2]["children"][0]["callout"]["rich_text"][0]["text"]["content"])
check("the note says how to reverse it", "undo" in
      appended[2]["children"][0]["callout"]["rich_text"][0]["text"]["content"])
receipt = json.load(open(fin.RECEIPT))
check("the receipt records the archive completed", receipt["archived"] is True)
check("it keeps the callout block undo must delete", receipt["callout_block"] == "callout-1")
check("it keeps the title undo must restore", receipt["previous_title"] == DB_TITLE)
check("it keeps the guard results as evidence", len(receipt["guards"]) == 6)
check("one notification, and it reports success",
      len(shell.notifications) == 1 and "finalized" in shell.notifications[0][0])

print("--- undo puts the board back ---")
api2 = FakeNotion()
api2.in_trash = True
api2.title = fin.nr.rt("Agent Content Inbox (frozen 2026-08-15 — migrated to Content DB)")
api2.description = fin.nr.rt("FROZEN ...")
raised, result, out, err = run(["undo"], api2, FakeShell())
check("exits clean", raised is None and result == 0)
restore = [c for c in api2.calls if c[0] == "PATCH" and c[1].startswith("/databases/")][0]
check("it is restored from the trash", restore[2]["in_trash"] is False)
check("the original title comes back", restore[2]["title"] == DB_TITLE)
check("the original (empty) description comes back", restore[2]["description"] == [])
check("the callout is deleted", api2.deleted_blocks == ["callout-1"])
check("the receipt is retired, not left to be replayed", not os.path.exists(fin.RECEIPT))
check("but it is kept for the record", os.path.exists(fin.RECEIPT + ".undone"))

print("--- every guard, on its own, refuses the pass with Notion untouched ---")
# Each row is a real way this could have gone wrong between now and 22:00 tomorrow.
cases = [
    ("something is still writing the old board",
     dict(notion=dict(inbox_rows=BASELINE + 1)), "old inbox unchanged"),
    ("a migrated row was trashed after the migration",
     dict(notion=dict(migrated=dict(
         {"new-%d" % i: {"parent": {"data_source_id": fin.nr.DATA_SOURCE_ID}}
          for i in range(BASELINE)}, **{"new-0": {"in_trash": True}}))),
     "migrated rows live"),
    ("a migrated row was moved off Content DB",
     dict(notion=dict(migrated=dict(
         {"new-%d" % i: {"parent": {"data_source_id": fin.nr.DATA_SOURCE_ID}}
          for i in range(BASELINE)}, **{"new-1": {"parent": {"data_source_id": "elsewhere"}}}))),
     "migrated rows live"),
    ("a migrated row cannot be resolved at all",
     dict(notion=dict(migrated={})), "migrated rows live"),
    ("the ledgers do not add up to the migrated set",
     dict(space=dict(ledger_entries=BASELINE - 1)), "ledgers readable"),
    ("a deployed caller still reads the old board",
     dict(space=dict(live_files={"content_change_dispatch.sh":
                                 "ds={}\n".format(fin.INBOX_DATA_SOURCE)})),
     "no live references"),
    ("the Content DB read path is broken",
     dict(shell=dict(board_rc=1)), "Content DB readable"),
    ("Content DB came back short — the migrated rows are not there",
     dict(shell=dict(board_rows=3)), "Content DB readable"),
    ("the nightly run failed", dict(shell=dict(unit_status="1")), "nightly run healthy"),
    ("the nightly run has not happened in over a day",
     dict(shell=dict(unit_age_h=fin.NIGHTLY_MAX_AGE_HOURS + 1)), "nightly run healthy"),
    ("Notion errored mid-guard rather than answering",
     dict(notion=dict(fail_on=("POST /data_sources",))), "old inbox unchanged"),
]
for desc, overrides, guard in cases:
    workspace(**overrides.get("space", {}))
    api = FakeNotion(**overrides.get("notion", {}))
    shell = FakeShell(**overrides.get("shell", {}))
    raised, result, out, err = run(["apply", "--notify"], api, shell)
    failed_guards = [line for line in out.splitlines() if line.startswith("FAIL ")]
    check("{} -> refuses".format(desc), result == 1 and raised is None)
    check("{} -> names the {!r} guard".format(desc, guard),
          any(guard in line for line in failed_guards))
    check("{} -> Notion is untouched".format(desc), api.writes() == [])
    check("{} -> no receipt is written".format(desc), not os.path.exists(fin.RECEIPT))
    check("{} -> Dave is told it refused".format(desc),
          len(shell.notifications) == 1 and "REFUSED" in shell.notifications[0][0])

print("--- the reference guard exempts the tools that operate ON the old board ---")
# This tool and the rollback tool both name the old data source by necessity. Once this
# one is deployed into bin/ it scans itself, so without the exemption the guard refuses
# every run — which is how it behaved on its first run from the deployed tree.
workspace()
raised, result, out, err = run(["check"], FakeNotion(), FakeShell())
check("a clean tree still passes with both operators present", result == 0)
check("and with a dated .bak that names it too",
      any("no live references" in line and line.startswith("PASS")
          for line in out.splitlines()))
check("the count of files actually scanned is reported, not assumed",
      any("live files scanned" in line for line in out.splitlines()))

print("--- a guard that cannot answer is a failure, not a crash ---")
# nr.api reports an HTTP error by calling sys.exit. `except Exception` does not catch
# SystemExit, so this is the difference between the refusal report and a bare stack.
# Both catch sites are exercised: the per-row one inside guard_migrated_rows_live, and
# the backstop in run_guards that covers the guards with no inner handling.
workspace()
api = FakeNotion(fail_on=("GET /pages",))
raised, result, out, err = run(["apply", "--notify"], api, FakeShell())
check("the per-row SystemExit is caught, not propagated", raised is None and result == 1)
check("the failing row is named, not just the guard",
      any("FAIL migrated rows live" in line and "new-0" in line and "GET /pages" in line
          for line in out.splitlines()))

workspace()
api = FakeNotion(fail_on=("POST /data_sources",))
raised, result, out, err = run(["apply", "--notify"], api, FakeShell())
check("the backstop catches a guard with no inner handling",
      raised is None and result == 1)
check("it reports what was raised",
      any("FAIL old inbox unchanged" in line and "raised SystemExit" in line
          for line in out.splitlines()))

print("--- check refuses the same way, and still writes nothing ---")
workspace()
api = FakeNotion(inbox_rows=BASELINE + 1)
raised, result, out, err = run(["check"], api, FakeShell())
check("non-zero exit", result == 1)
check("nothing written", api.writes() == [])

print("--- a failure between freeze and archive stays reversible ---")
# The freeze is two writes and the archive is a third. If the receipt were written after
# all three, a failure here would leave a renamed board that undo cannot find.
workspace()
api = FakeNotion(fail_on=("PATCH /databases/{}".format(fin.INBOX_DATABASE),))
api._fail_on = ()
original_call = api.__call__
state = {"patches": 0}


def fail_on_archive(method, path, token, payload=None, timeout=30):
    if method == "PATCH" and path.startswith("/databases/") and "in_trash" in (payload or {}):
        raise SystemExit("Notion API 502 on archive: simulated")
    return original_call(method, path, token, payload, timeout)


shell = FakeShell()
raised, result, out, err = run(["apply", "--notify"], fail_on_archive, shell)
check("the failure is not swallowed", isinstance(raised, SystemExit))
check("a receipt exists anyway", os.path.exists(fin.RECEIPT))
partial = json.load(open(fin.RECEIPT))
check("it records that the archive did NOT happen", partial["archived"] is False)
check("it still carries what undo needs",
      partial["callout_block"] == "callout-1" and partial["previous_title"] == DB_TITLE)
check("Dave is told it failed part-way, and how to reverse it",
      len(shell.notifications) == 1 and "FAILED PART-WAY" in shell.notifications[0][0]
      and "undo" in shell.notifications[0][1])

print("--- an archive that silently did not stick is a failure ---")
# PATCH returning 200 is not evidence. If in_trash reads false afterwards, the board is
# still live and reporting success would tell Dave step 5 was done when it was not.
workspace()
api = FakeNotion(archive_sticks=False)
raised, result, out, err = run(["apply", "--notify"], api, FakeShell())
check("it raises rather than reporting success", isinstance(raised, RuntimeError))
check("the receipt does not claim the archive happened",
      json.load(open(fin.RECEIPT))["archived"] is False)

print("--- apply without --notify stays silent ---")
workspace()
shell = FakeShell()
raised, result, out, err = run(["apply"], FakeNotion(), shell)
check("exits clean", raised is None and result == 0)
check("no notification", shell.notifications == [])

print("--- systemctl output is parsed by key, never by position ---")
# `systemctl show -p A -p B` prints in systemd's own order, so a positional read of a
# multi-property call swaps the fields and misjudges the unit. FakeShell emits an extra
# leading line precisely so a positional parser would fail this.
workspace()
run(["check"], FakeNotion(), FakeShell())
check("the status is read from its own key",
      fin.unit_property(fin.NIGHTLY_UNIT, "ExecMainStatus") == "0")
check("the timestamp is read from its own key",
      fin.unit_property(fin.NIGHTLY_UNIT, "ExecMainExitTimestamp").startswith("@"))
check("an absent property is empty, not the neighbouring line's value",
      fin.unit_property(fin.NIGHTLY_UNIT, "NoSuchProperty") == "")

print("--- a notify.sh that fails cannot fail the run ---")
# The pass is done by then. Turning a completed finalize into a failed unit would send
# Dave to check a board that is already correct.
workspace()


class BrokenNotify(FakeShell):
    def __call__(self, argv, **kw):
        if argv[0] == fin.NOTIFY:
            raise OSError("notify.sh: not found")
        return FakeShell.__call__(self, argv, **kw)


raised, result, out, err = run(["apply", "--notify"], FakeNotion(), BrokenNotify())
check("the run still succeeds", raised is None and result == 0)
check("the delivery failure is surfaced on stderr", "notify failed" in err)

print("--- the canary: a pipeline condition that fails open would hide all of the above ---")
check("canary", True)

if failures:
    print("\n{} FAILED".format(len(failures)))
    raise SystemExit(1)
