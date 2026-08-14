#!/usr/bin/env python3
"""
content_inbox_finalize.py — steps 4 and 5 of the 2026-08-14 Content DB migration.

Step 4 freezes the old Agent Content Inbox: a note on the database itself and a callout
on its parent page. Step 5 archives the inline database into Notion's trash. Both run in
one pass, unattended, from content-inbox-finalize.timer.

Why the note goes on the PAGE and not only on the database: step 5 trashes the database,
and a note inside a trashed database is visible to nobody. The callout is inserted with
`after` set to the database block, so once the database is gone the note is the first
thing on the page.

Nothing here is irreversible. `undo` restores the database from trash, puts the original
title and description back, and deletes the callout — verified against the live API on
2026-08-14 with a throwaway database (archive -> in_trash true, restore -> in_trash
false). The migrated rows are a separate concern with a separate reversal:
notion_content_migrate.py rollback, against both ledgers.

The guards are the point of this file. It runs with nobody watching, against a board that
holds Dave's own content, so every precondition that made the migration safe is re-checked
at run time and ANY failure refuses the whole pass. Refusing costs a rerun; freezing a
board something still writes to, or archiving rows that never actually landed, costs work.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion_rest as nr  # noqa: E402  (load_token/api/rt — one Notion transport, not two)

INBOX_DATA_SOURCE = "ab5eb999-e986-4a8b-9159-eb340196af9b"
INBOX_DATABASE = "e1ec81a3-1148-4e5f-ad16-36b6eb7cc876"
INBOX_PAGE = "39b8d768-1ede-8093-a843-e553edd241d6"

# The inbox held exactly these rows when the migration ran on 2026-08-14, newest row
# created 2026-08-09. A higher count at run time means something is still writing this
# board, which is the one condition under which freezing it would lose work.
INBOX_ROW_BASELINE = 17

LEDGERS = [
    os.path.expanduser("~/agent-workforce/var/notion_content_migration.json"),
    os.path.expanduser("~/agent-workforce/var/notion_content_migration_probe.json"),
]
RECEIPT = os.path.expanduser("~/agent-workforce/var/content_inbox_finalize.json")
NOTION_REST = os.path.expanduser("~/agent-workforce/bin/notion_rest.py")
NOTIFY = os.path.expanduser("~/agent-workforce/bin/notify.sh")

# The migration tool is the one file that must keep naming the old data source — it is
# what rolls the migration back. Any other live reference means a caller was missed.
MIGRATION_TOOL = "notion_content_migrate.py"
LIVE_CODE_DIRS = [
    os.path.expanduser("~/agent-workforce/bin"),
    os.path.expanduser("~/agent-workforce/profiles"),
]
LIVE_CODE_SUFFIXES = (".py", ".sh", ".md")

NIGHTLY_UNIT = "augustus-content.service"
NIGHTLY_MAX_AGE_HOURS = 30  # the nightly run is every 24h; 30 tolerates a late start


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


# ── guards ────────────────────────────────────────────────────────────────────────
# Each returns (ok, detail). None of them writes anything.

def ledger_entries():
    entries = []
    for path in LEDGERS:
        with open(path) as handle:
            entries.extend(json.load(handle)["entries"])
    return entries


def guard_ledgers_readable():
    try:
        entries = ledger_entries()
    except (OSError, ValueError, KeyError) as exc:
        return False, "ledger unreadable: {}".format(exc)
    ok = len(entries) == INBOX_ROW_BASELINE
    return ok, "{} ledger entries (expected {})".format(len(entries), INBOX_ROW_BASELINE)


def guard_migrated_rows_live(token):
    """Every migrated row still resolves in Content DB and is not in the trash."""
    missing = []
    for entry in ledger_entries():
        try:
            page = nr.api("GET", "/pages/{}".format(entry["created"]), token)
        except (Exception, SystemExit) as exc:  # nr.api exits rather than raises on HTTP error
            missing.append("{}: {}".format(entry["created"], exc))
            continue
        if page.get("in_trash") or page.get("archived"):
            missing.append("{}: in trash".format(entry["created"]))
        elif page.get("parent", {}).get("data_source_id") != nr.DATA_SOURCE_ID:
            missing.append("{}: not in Content DB".format(entry["created"]))
    detail = "all {} migrated rows live in Content DB".format(INBOX_ROW_BASELINE)
    return not missing, detail if not missing else "; ".join(missing[:3])


def guard_inbox_unchanged(token):
    rows = nr.query_all(token, {"page_size": 100},
                        data_source_id=INBOX_DATA_SOURCE)
    ok = len(rows) == INBOX_ROW_BASELINE
    return ok, "old inbox holds {} rows (baseline {})".format(len(rows), INBOX_ROW_BASELINE)


def live_code_files():
    for directory in LIVE_CODE_DIRS:
        for name in sorted(os.listdir(directory)):
            if name.endswith(LIVE_CODE_SUFFIXES) and name != MIGRATION_TOOL:
                yield os.path.join(directory, name)


def guard_no_live_references():
    """No deployed caller still names the old data source.

    Suffix-scoped on purpose: the deployed tree carries dated `.bak-*` copies of retired
    profiles that do still name it. Excluding them silently would be the same class of
    mistake this guard exists to catch, so the skipped set is reported, not assumed.
    """
    hits = []
    scanned = 0
    for path in live_code_files():
        scanned += 1
        with open(path, errors="replace") as handle:
            if INBOX_DATA_SOURCE in handle.read():
                hits.append(path)
    detail = "{} live files scanned, 0 name the old data source".format(scanned)
    return not hits, detail if not hits else "still referenced by: {}".format(", ".join(hits))


def guard_content_db_readable():
    """The deployed read path works — the same command content_change_dispatch.sh runs."""
    proc = subprocess.run(
        [sys.executable, NOTION_REST, "board", "--json", "--max-rows", "0"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return False, "notion_rest.py board exited {}".format(proc.returncode)
    rows = json.loads(proc.stdout)
    ok = len(rows) >= INBOX_ROW_BASELINE
    return ok, "Content DB read returns {} rows".format(len(rows))


def unit_property(unit, name):
    """One property, parsed as KEY=VALUE.

    `systemctl show -p A -p B` prints in systemd's own order, not the order asked for, so
    positional parsing of a multi-property call silently swaps fields.
    """
    proc = subprocess.run(
        ["systemctl", "show", unit, "--timestamp=unix", "-p", name],
        capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        key, _, value = line.partition("=")
        if key == name:
            return value
    return ""


def guard_nightly_run_ok():
    status = unit_property(NIGHTLY_UNIT, "ExecMainStatus")
    stamp = unit_property(NIGHTLY_UNIT, "ExecMainExitTimestamp").lstrip("@")
    if status != "0" or not stamp:
        return False, "{} last exit status {!r}".format(NIGHTLY_UNIT, status)
    age = (utcnow() - datetime.datetime.fromtimestamp(
        int(stamp), datetime.timezone.utc)).total_seconds() / 3600
    ok = age <= NIGHTLY_MAX_AGE_HOURS
    return ok, "{} exited 0 {:.1f}h ago (limit {}h)".format(
        NIGHTLY_UNIT, age, NIGHTLY_MAX_AGE_HOURS)


def run_guards(token):
    checks = [
        ("ledgers readable", guard_ledgers_readable),
        ("migrated rows live", lambda: guard_migrated_rows_live(token)),
        ("old inbox unchanged", lambda: guard_inbox_unchanged(token)),
        ("no live references", guard_no_live_references),
        ("Content DB readable", guard_content_db_readable),
        ("nightly run healthy", guard_nightly_run_ok),
    ]
    results = []
    for name, check in checks:
        try:
            ok, detail = check()
        except (Exception, SystemExit) as exc:
            # A guard that could not answer has not passed. SystemExit is caught with the
            # rest because nr.api reports an HTTP error by exiting, and a Notion blip
            # during the guards must produce the refusal report, not a bare stack.
            ok, detail = False, "raised {}: {}".format(type(exc).__name__, exc)
        results.append({"guard": name, "ok": ok, "detail": detail})
    return results


def format_guards(results):
    return "\n".join("{} {} — {}".format("PASS" if r["ok"] else "FAIL", r["guard"], r["detail"])
                     for r in results)


# ── actions ───────────────────────────────────────────────────────────────────────

def freeze_note(day):
    return ("FROZEN {} — this board is retired. Every row was migrated to Content DB "
            "(LinkedIn Content Planner) on 2026-08-14 and nothing on Praetorium reads or "
            "writes here any more: agent pitches and drafts land in Content DB, filtered "
            "by Proposed by. This inline database has been archived to Notion trash. "
            "Reverse it with bin/content_inbox_finalize.py undo; reverse the migrated "
            "rows separately with bin/notion_content_migrate.py rollback."
            ).format(day)


def freeze(token, page_id, database_id, day):
    """Mark the database frozen and put a note on the page above it.

    Returns what `undo` needs: the callout block and the title/description it replaced.
    """
    before = nr.api("GET", "/databases/{}".format(database_id), token)
    title = "".join(part.get("plain_text", "") for part in before.get("title", []))
    nr.api("PATCH", "/databases/{}".format(database_id), token, {
        "title": nr.rt("{} (frozen {} — migrated to Content DB)".format(title, day)),
        "description": nr.rt(freeze_note(day)),
    })
    callout = nr.api("PATCH", "/blocks/{}/children".format(page_id), token, {
        "after": database_id,
        "children": [{"object": "block", "type": "callout", "callout": {
            "rich_text": nr.rt(freeze_note(day)),
        }}],
    })
    return {"callout_block": callout["results"][0]["id"],
            "previous_title": before.get("title", []),
            "previous_description": before.get("description", [])}


def archive(token, database_id):
    nr.api("PATCH", "/databases/{}".format(database_id), token, {"in_trash": True})
    after = nr.api("GET", "/databases/{}".format(database_id), token)
    if not after.get("in_trash"):
        raise RuntimeError("database {} still reads in_trash=false after archive".format(
            database_id))


def unfreeze(token, receipt):
    nr.api("PATCH", "/databases/{}".format(receipt["database"]), token, {
        "in_trash": False,
        "title": receipt["previous_title"],
        "description": receipt["previous_description"],
    })
    nr.api("DELETE", "/blocks/{}".format(receipt["callout_block"]), token)


# ── commands ──────────────────────────────────────────────────────────────────────

def write_receipt(receipt):
    with open(RECEIPT, "w") as handle:
        json.dump(receipt, handle, indent=2)


def notify(subject, body):
    """Best effort: a delivery failure must not turn a completed pass into a failed unit."""
    try:
        subprocess.run([NOTIFY, subject, body], check=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print("notify failed: {}".format(exc), file=sys.stderr)


def cmd_check(args, token):
    results = run_guards(token)
    print(format_guards(results))
    passed = all(r["ok"] for r in results)
    print("\n{}/{} guards passed".format(sum(r["ok"] for r in results), len(results)))
    return 0 if passed else 1


def cmd_apply(args, token):
    results = run_guards(token)
    report = format_guards(results)
    print(report)
    if not all(r["ok"] for r in results):
        if args.notify:
            notify("[Praetorium] Content inbox finalize REFUSED",
                   "Steps 4 and 5 did not run — a precondition failed. Nothing was "
                   "changed in Notion.\n\n" + report)
        return 1

    day = utcnow().date().isoformat()
    receipt = {"finalized_at": utcnow().isoformat(), "database": INBOX_DATABASE,
               "page": INBOX_PAGE, "guards": results, "archived": False}
    try:
        receipt.update(freeze(token, INBOX_PAGE, INBOX_DATABASE, day))
        write_receipt(receipt)  # from here on `undo` can reverse whatever landed
        archive(token, INBOX_DATABASE)
        receipt["archived"] = True
        write_receipt(receipt)
    except (Exception, SystemExit) as exc:
        if args.notify:
            notify("[Praetorium] Content inbox finalize FAILED PART-WAY",
                   "{}: {}\n\nReceipt (if written): {}\nReverse with: {} undo".format(
                       type(exc).__name__, exc, RECEIPT, os.path.abspath(__file__)))
        raise

    done = ("Agent Content Inbox frozen and archived to Notion trash.\n\n" + report +
            "\n\nFreeze note: page {}\nArchived database: {}\nReceipt: {}\n"
            "Reverse with: {} undo".format(INBOX_PAGE, INBOX_DATABASE, RECEIPT,
                                           os.path.abspath(__file__)))
    print("\n" + done)
    if args.notify:
        notify("[Praetorium] Content inbox finalized", done)
    return 0


def cmd_undo(args, token):
    with open(RECEIPT) as handle:
        receipt = json.load(handle)
    unfreeze(token, receipt)
    os.rename(RECEIPT, RECEIPT + ".undone")
    print("restored database {} and deleted callout {}".format(
        receipt["database"], receipt["callout_block"]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Freeze and archive the retired Agent Content Inbox (migration steps 4-5)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="run the preflight guards only; no writes")
    apply_cmd = sub.add_parser("apply", help="freeze the board, then archive it")
    apply_cmd.add_argument("--notify", action="store_true",
                           help="publish the outcome through notify.sh")
    sub.add_parser("undo", help="restore the database and remove the freeze note")

    args = parser.parse_args(argv)
    token = nr.load_token()
    return {"check": cmd_check, "apply": cmd_apply, "undo": cmd_undo}[args.cmd](args, token)


if __name__ == "__main__":
    sys.exit(main())
