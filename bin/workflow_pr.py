#!/usr/bin/env python3
"""The proposal worker (T5.3b): a schedule change or a retirement, planned on a detached
worktree of origin/main in a dedicated bare clone, checked, recorded, and — only on a submit
that carries a fresh preview token whose diff bytes still match — committed to a
`control-room/<kind>-<id>-<stamp>` branch, pushed, and opened as a PR with `gh`. Nothing here
edits the box checkout, the runtime tree, /etc or `main`; `clear` is the one exception, it
writes one registry line into ~/dev/agent-workforce by Dave's hand at land.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import getpass
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import control_room_api as api  # noqa: E402
import workflow_pr_body as body  # noqa: E402
import workflow_pr_checks as checks  # noqa: E402
import workflow_pr_git as prgit  # noqa: E402
import workflow_pr_record as record  # noqa: E402
import workflow_pr_schedule as schedule  # noqa: E402
from workflow_pr_record import Refused  # noqa: E402

PREVIEW_TTL_SECONDS = record.PREVIEW_TTL_SECONDS
LOCK_TIMEOUT_SECONDS = 120
STAGE_BUDGET_SECONDS = 300
DEFAULT_GH_REPO = "Dave1524/Hermes_Agent_Workforce_Praetorium"
DEFAULT_AUTHOR = "Praetorium Control Room <dave.hamelink@vantagepointconsulting.nl>"
STAGES = ("preview", "submit", "list")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def read_timezone() -> dict[str, str]:
    try:
        done = subprocess.run(["timedatectl", "show", "-p", "Timezone", "--value"], capture_output=True, text=True, timeout=10)
        if done.returncode == 0 and done.stdout.strip():
            return {"name": done.stdout.strip(), "source": "timedatectl"}
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        return {"name": pathlib.Path("/etc/timezone").read_text().strip(), "source": "/etc/timezone"}
    except OSError:
        return {"name": os.environ.get("TZ") or "UTC", "source": "TZ"}


def cli_actor() -> dict[str, Any]:
    user = os.environ.get("SUDO_USER") or getpass.getuser()
    return {"kind": "cli", "user": user, "label": f"{user} via workflow_pr.py"}


class Worker:
    def __init__(self, state_root: pathlib.Path | str, remote: str, gh_repo: str = DEFAULT_GH_REPO, author: str = DEFAULT_AUTHOR,
                 clock: Callable[[], dt.datetime] = utc_now, runner: checks.Runner | None = None,
                 tz_reader: Callable[[], dict[str, str]] | None = None, calendar_runner: schedule.CalendarRunner | None = None,
                 live: dict[str, Any] | None = None) -> None:
        self.state = pathlib.Path(state_root)
        self.remote, self.gh_repo, self.author, self.clock = remote, gh_repo, author, clock
        self.runner = runner or checks.subprocess_runner
        self.tz_reader = tz_reader or read_timezone
        self.calendar_runner = calendar_runner or schedule.systemd_analyze_calendar
        self.live = live or {}
        self.git = prgit.GitRepo(self.state, remote, author)

    # --- health -------------------------------------------------------------------------------
    def unavailable(self) -> str | None:
        if not self.state.is_dir() or not os.access(self.state, os.W_OK):
            return f"state root {self.state} missing or unwritable — run: bin/workflow_pr.py doctor"
        if not (self.state / "repo.git" / "HEAD").exists():
            return f"{self.state}/repo.git missing — run: bin/workflow_pr.py init (then doctor)"
        if shutil.which("gh") is None:
            return "gh is not on PATH — run: bin/workflow_pr.py doctor"
        return None

    def doctor(self) -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = []
        writable = self.state.is_dir() and os.access(self.state, os.W_OK)
        lines.append(("ok" if writable else "fail", f"state root {self.state} " + ("writable" if writable else "missing or unwritable")))
        if (self.state / "repo.git" / "HEAD").exists():
            lines.append(("ok", "repo.git present"))
            try:
                self.git.init()
                lines.append(("ok", f"repo.git origin is {self.remote}"))
                self.git.run(["ls-remote", "--heads", "origin", "main"], timeout=prgit.TRANSFER_TIMEOUT_SECONDS)
                lines.append(("ok", "remote reachable (ls-remote main)"))
            except prgit.GitFailed as exc:
                lines.append(("fail", str(exc)))
        else:
            lines.append(("fail", "repo.git missing — run: bin/workflow_pr.py init"))
        for tool in ("git", "gh", "systemd-analyze"):
            lines.append(("ok", f"{tool} on PATH: {shutil.which(tool)}") if shutil.which(tool) else ("fail", f"{tool} not on PATH"))
        if shutil.which("gh"):
            code, _, err = self._gh(["auth", "status"], log=None)
            lines.append(("ok", "gh auth status") if code == 0 else ("fail", f"gh auth status exited {code}: {err.strip()[:200]}"))
        tz = self.tz_reader()
        lines.append(("ok", f"timezone {tz['name']} ({tz['source']})"))
        return lines

    def init(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        self.git.init()

    # --- stages -------------------------------------------------------------------------------
    def list(self, workflow_id: str, kind: str) -> dict[str, Any]:
        return {"stage": "list", "items": record.list_records(self.state, workflow_id, kind)}

    def preview(self, request: dict[str, Any], actor: dict[str, Any], live_item: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._stage("preview", request, actor, live_item)

    def submit(self, request: dict[str, Any], actor: dict[str, Any], live_item: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._stage("submit", request, actor, live_item)

    def _stage(self, stage: str, request: dict[str, Any], actor: dict[str, Any], live_item: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        now = self.clock()
        rec = record.new_record(request["kind"], request["workflow_id"], actor, request.get("reason"), now)
        rec["proposed"] = request.get("proposed")
        try:
            prior = self._prior(stage, request, rec)
            self._validate(request, rec)
            with self._lock():
                response = self._run_locked(stage, request, rec, live_item, prior, now)
        except Refused as refusal:
            response = self._refused(rec, refusal)
        rec["completed_at"] = record.stamp(self.clock())
        record.write(self.state, rec)
        response["record"] = {k: v for k, v in rec.items() if k not in ("diff",)}
        return rec, response

    def _run_locked(self, stage: str, request: dict[str, Any], rec: dict[str, Any], live_item: dict[str, Any] | None,
                    prior: dict[str, Any] | None, now: dt.datetime) -> dict[str, Any]:
        """Everything that touches the clone, including the command-log snapshot: one Worker serves
        every request thread, so the log is read and cleared under the same lock that fills it."""
        pid = rec["proposal_id"]
        try:
            self._prepare(rec)
            worktree = self.git.worktree_add(pid)
            try:
                response = self._plan_and_check(stage, rec, request, worktree, live_item, prior, now)
                if stage == "submit":
                    response = self._push_and_open(rec, worktree, response)
            finally:
                self.git.cleanup(pid, rec.get("branch") if stage == "submit" else None)
        except Refused as refusal:
            response = self._refused(rec, refusal)
        except prgit.GitFailed as failure:
            rec.update(stage="failed", refusal={"code": "failed", "message": str(failure)})
            response = {"error": str(failure), "record": None, "branch_pushed": bool(rec.get("branch_pushed"))}
        except Exception as failure:  # noqa: BLE001 — an unrecorded traceback is the one outcome worse than a failed record
            message = f"{type(failure).__name__}: {failure}"
            rec.update(stage="failed", refusal={"code": "failed", "message": message})
            response = {"error": message, "record": None, "branch_pushed": bool(rec.get("branch_pushed"))}
        rec["commands"] = list(self.git.commands)
        self.git.commands.clear()
        return response

    @staticmethod
    def _refused(rec: dict[str, Any], refusal: "Refused") -> dict[str, Any]:
        rec.update(stage="refused", refusal=refusal.as_dict())
        if refusal.diff is not None:
            rec["diff"] = refusal.diff
        return {"error": refusal.as_dict(), "record": None}

    def _prior(self, stage: str, request: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any] | None:
        if stage != "submit":
            return None
        token = request.get("preview_token")
        prior = record.find(self.state, token) if isinstance(token, str) else None
        if prior is None or prior["workflow_id"] != request["workflow_id"] or prior["kind"] != request["kind"]:
            raise Refused("preview_required", "submit needs the preview_token of a preview for this workflow and kind")
        valid, why = record.token_valid(prior, self.clock())
        if not valid:
            raise Refused("preview_stale" if why == "preview expired" else "preview_required", f"preview {token}: {why}")
        if rec.get("proposed") is None:
            rec["proposed"] = prior.get("proposed")
        return prior

    def _validate(self, request: dict[str, Any], rec: dict[str, Any]) -> None:
        """Shape rules that need no git call: a reason for both kinds, the retention decision for retire."""
        reason = rec.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise Refused("bad_request", "reason is required")
        if not record.single_line(reason):
            raise Refused("bad_request", "reason must be one line: it is written into a manifest comment and a TOML string")
        if request["kind"] == "retire":
            import workflow_pr_retire as retire
            retire.validate_request(reason, rec.get("proposed"))

    def _prepare(self, rec: dict[str, Any]) -> None:
        reason = self.unavailable()
        if reason:
            raise Refused("worker_unavailable", reason)
        self.git.init()
        self.git.fetch_main()
        rec["base"] = {"remote": self.remote, "ref": "refs/remotes/origin/main", "sha": self.git.base_sha()}
        self.git.worktree_remove("base")
        self.git.worktree_add("base")

    def _item(self, worktree: pathlib.Path, workflow_id: str, live_item: dict[str, Any] | None) -> dict[str, Any]:
        root = worktree.resolve()
        receipts = pathlib.Path(self.live.get("receipts") or root / "var" / "workflow-receipts")
        model = api.ControlRoomReadModel(paths=api.SourcePaths(repo=root, runtime=root, receipts=receipts),
                                         systemd=_NullSystemd(), clock=self.clock, calendar_runner=lambda spec: [])
        item = model.workflow_detail(workflow_id)[0]
        if item is None:
            raise Refused("unknown_workflow", f"{workflow_id} is not a workflow in origin/main")
        if live_item:
            for key in ("control", "lastValidArtifact", "validArtifactRate", "benefit", "lastRun"):
                if key in live_item:
                    item[key] = live_item[key]
        return item

    def _plan_and_check(self, stage: str, rec: dict[str, Any], request: dict[str, Any], worktree: pathlib.Path,
                        live_item: dict[str, Any] | None, prior: dict[str, Any] | None, now: dt.datetime) -> dict[str, Any]:
        # Submit re-plans under the preview's id AND clock: the dates the plan stamps into the diff
        # must match the preview byte-for-byte, or a submit past UTC midnight reads as stale.
        pid = prior["proposal_id"] if prior else rec["proposal_id"]
        plan_now = record.parse_stamp(prior["requested_at"]) if prior else now
        item = self._item(worktree, request["workflow_id"], live_item)
        proposed = rec.get("proposed") if rec.get("proposed") is not None else {}
        if request["kind"] == "schedule":
            plan = schedule.plan_schedule(worktree, item, proposed, plan_now, pid, self.tz_reader(), self.calendar_runner)
        else:
            import workflow_pr_retire as retire
            plan = retire.plan_retire(worktree, item, {**proposed, "reason": rec.get("reason")}, plan_now, pid, self.live)
        text, stat, files = self.git.diff(worktree)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stamp = pid.split("-", 1)[0]
        branch = prior["branch"] if prior else f"control-room/{request['kind']}-{record.slug(request['workflow_id'])}-{stamp}"
        rec.update(branch=branch, files=files, diff=text, diff_sha256=sha, diff_stat=stat.strip(), description=plan.description,
                   retention=plan.context().get("retention"))
        if prior and prior["diff_sha256"] != sha:
            raise Refused("preview_stale", "the diff no longer matches the preview byte-for-byte (origin/main moved, or the request changed); preview again", diff=text)
        ctx = {**plan.context(), "base_worktree": str(self.git.work / "base"), "subject_paths": plan.context().get("subject_paths", []),
               "runtime_root": (self.live or {}).get("runtime_root")}
        results = checks.run_checks(worktree, request["kind"], ctx, self.runner)
        rec["checks"] = results
        rec["residue"] = plan.context().get("residue")
        acknowledge = bool(proposed.get("acknowledge_pinned_tests", False)) if isinstance(proposed, dict) else False
        allowed, blockers = checks.submit_allowed(results, request["kind"], acknowledge)
        rec["stage"] = "previewed"
        rec["draft"] = checks.draft_required(results, acknowledge)
        expires = record.stamp(now + dt.timedelta(seconds=PREVIEW_TTL_SECONDS))
        response = {"stage": "preview", "proposal_id": rec["proposal_id"], "preview_token": pid, "expires_at": expires, "base": rec["base"],
                    "branch": branch, "summary": plan.summary, "description": plan.description, "files": files, "diff": text,
                    "diff_sha256": sha, "checks": results, "residue": rec["residue"], "retention": rec["retention"],
                    "submit_allowed": allowed, "submit_blockers": blockers}
        if stage == "submit" and not allowed:
            code = "residue_in_branch" if any(b.startswith("residue_in_branch") for b in blockers) else "checks_failed"
            raise Refused(code, "; ".join(blockers))
        return response

    def _push_and_open(self, rec: dict[str, Any], worktree: pathlib.Path, preview: dict[str, Any]) -> dict[str, Any]:
        branch = rec["branch"]
        prefix = branch.rsplit("-", 1)[0] + "-"
        same_workflow = re.compile(re.escape(prefix) + r"\d{8}T\d{6}Z$")  # not a slug this one merely extends
        open_prs = self._open_proposals(same_workflow, rec)
        if open_prs:
            raise Refused("open_proposal_exists", f"an open proposal already exists for {rec['workflow_id']}: {open_prs[0]}", choices=open_prs)
        orphans = [head for head in self.git.remote_heads(prefix) if same_workflow.match(head)]
        if orphans:
            raise Refused("open_proposal_exists",
                          f"branch {orphans[0]} is on the remote without an open pull request (a submit failed after its push): "
                          f"open its PR by hand or delete it (gh api -X DELETE repos/{self.gh_repo}/git/refs/heads/{orphans[0]}), then submit again",
                          choices=orphans)
        self.git.commit(worktree, branch, body.commit_message(rec))
        self.git.push_guarded(branch, cwd=worktree)
        rec["branch_pushed"] = True
        body_path = self.git.work / f"{rec['proposal_id']}.body.md"
        body_path.write_text(body.body(rec), encoding="utf-8")
        argv = ["pr", "create", "--repo", self.gh_repo, "--base", "main", "--head", branch, "--title", body.title(rec), "--body-file", str(body_path)]
        if rec.get("draft"):
            argv.append("--draft")
        code, out, err = self._gh(argv, rec)
        body_path.unlink(missing_ok=True)
        if code != 0:
            raise prgit.GitFailed(f"gh pr create failed ({code}) after pushing {branch}: {err.strip()[-300:]}", ["gh", *argv], code, err)
        url = out.strip().splitlines()[-1] if out.strip() else ""
        number = int(url.rsplit("/", 1)[-1]) if url.rsplit("/", 1)[-1].isdigit() else None
        rec.update(stage="submitted", pr={"url": url, "number": number, "branch": branch, "draft": bool(rec.get("draft"))})
        return {"stage": "submitted", "proposal_id": rec["proposal_id"], "pr": rec["pr"], "diff_sha256": rec["diff_sha256"]}

    def _open_proposals(self, same_workflow: "re.Pattern[str]", rec: dict[str, Any]) -> list[str]:
        """Fails closed: a `gh pr list` that errors refuses the submit rather than reporting no PR."""
        argv = ["pr", "list", "--repo", self.gh_repo, "--json", "url,headRefName", "--state", "open", "--limit", "500"]
        code, out, err = self._gh(argv, rec)
        if code != 0:
            raise prgit.GitFailed(f"gh pr list failed ({code}) before the push: {err.strip()[-300:]}", ["gh", *argv], code, err)
        try:
            rows = json.loads(out or "[]")
        except ValueError as exc:
            raise prgit.GitFailed(f"gh pr list printed no JSON: {exc}", ["gh", *argv], code, out) from exc
        return [row.get("url", "") for row in rows if same_workflow.match(str(row.get("headRefName", "")))]

    def _gh(self, args: list[str], log: dict[str, Any] | None) -> tuple[int, str, str]:
        env = {**self.git._env(), "GH_NO_UPDATE_NOTIFIER": "1", "GH_PROMPT_DISABLED": "1"}
        started = time.monotonic()
        try:
            done = subprocess.run(["gh", *args], capture_output=True, text=True, env=env, timeout=prgit.TRANSFER_TIMEOUT_SECONDS)
            code, out, err = done.returncode, done.stdout, done.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, out, err = 127, "", str(exc)
        self.git.commands.append({"argv": ["gh", *args], "exit": code, "seconds": round(time.monotonic() - started, 3), "stderr": err.strip()[-2000:]})
        return code, out, err

    class _Lock:
        def __init__(self, path: pathlib.Path) -> None:
            self.path, self.handle = path, None

        def __enter__(self) -> "Worker._Lock":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(self.path, "a+")
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except OSError:
                    if time.monotonic() > deadline:
                        self.handle.close()
                        raise Refused("locked", f"another proposal held {self.path} for more than {LOCK_TIMEOUT_SECONDS}s")
                    time.sleep(0.2)

        def __exit__(self, *_: Any) -> None:
            if self.handle:
                fcntl.flock(self.handle, fcntl.LOCK_UN)
                self.handle.close()

    def _lock(self) -> "Worker._Lock":
        return Worker._Lock(self.state / "lock")


class _NullSystemd:
    """The worker's read model runs over a checkout, not the box: every unit is unknown."""

    def show(self, name: str, scope: str) -> tuple[dict[str, Any], str | None]:
        return {}, f"Unit {name} could not be found."


# --- CLI ---------------------------------------------------------------------------------------
def _worker(args: argparse.Namespace) -> Worker:
    state = args.state or os.environ.get("CONTROL_ROOM_PROPOSALS_ROOT") or os.path.expanduser("~/agent-workforce/var/control-proposals")
    remote = args.remote or os.environ.get("CONTROL_ROOM_PROPOSALS_REMOTE") or f"https://github.com/{DEFAULT_GH_REPO}.git"
    clock = (lambda: dt.datetime.fromisoformat(args.now.replace("Z", "+00:00"))) if args.now else utc_now
    return Worker(state, remote, os.environ.get("CONTROL_ROOM_GH_REPO", DEFAULT_GH_REPO), os.environ.get("CONTROL_ROOM_GIT_AUTHOR", DEFAULT_AUTHOR),
                  clock=clock, live=live_trees())


def live_trees() -> dict[str, str]:
    """The box's deployed and installed trees a live residue scan reads; `checkout` is read by `clear` alone."""
    return {"runtime_root": os.path.expanduser("~/agent-workforce"), "etc_dir": "/etc/systemd/system",
            "user_tree": os.path.expanduser("~/.config/systemd/user"), "checkout": os.path.expanduser("~/dev/agent-workforce")}


def _print_stage(rec: dict[str, Any], response: dict[str, Any]) -> int:
    if rec["stage"] == "previewed":
        print(f"preview {rec['proposal_id']} on {rec['base']['sha'][:12]} → {rec['branch']}\n{response.get('summary', '')}\n")
        print(json.dumps(response.get("description"), indent=2))
        print("\n" + (rec.get("diff") or ""))
        for check in rec["checks"]:
            print(f"{check['status']:>5}  {check['id']} [{check['class']}]  {check['output'].splitlines()[0] if check['output'] else ''}")
        print("\nsubmit_allowed:", response.get("submit_allowed"), *response.get("submit_blockers", []), sep="\n  ")
        print(f"\nsubmit with: --submit {rec['proposal_id']}")
        return 0
    if rec["stage"] == "submitted":
        print(f"submitted · {rec['kind']} · {rec['workflow_id']} · PR #{rec['pr']['number']}\n{rec['pr']['url']}")
        return 0
    print(f"{rec['stage']}: {json.dumps(rec.get('refusal'))}", file=sys.stderr)
    return 1


def _request(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "schedule":
        proposed: dict[str, Any] = {"on_calendar": args.on_calendar, "randomized_delay_sec": args.delay,
                                    "persistent": None if args.persistent is None else args.persistent == "yes", "trigger": args.trigger,
                                    "manifest_trigger": None, "contract_trigger": None, "acknowledge_pinned_tests": args.acknowledge_pinned_tests}
    else:
        proposed = {"artifact_retention": {"receipts": args.receipts, "notion": args.notion, "inbox": args.inbox, "note": args.note},
                    "acknowledge_pinned_tests": args.acknowledge_pinned_tests}
    return {"workflow_id": args.workflow_id, "kind": args.command, "reason": args.reason, "stage": "submit" if args.submit else "preview",
            "preview_token": args.submit, "proposed": proposed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state"), parser.add_argument("--remote"), parser.add_argument("--now")
    sub = parser.add_subparsers(dest="command", required=True)
    for kind in ("schedule", "retire"):
        p = sub.add_parser(kind)
        p.add_argument("workflow_id"), p.add_argument("--reason", required=True)
        p.add_argument("--preview", action="store_true"), p.add_argument("--submit", metavar="TOKEN")
        p.add_argument("--acknowledge-pinned-tests", action="store_true")
        if kind == "schedule":
            p.add_argument("--on-calendar", action="append", required=True), p.add_argument("--delay"), p.add_argument("--persistent", choices=("yes", "no"))
            p.add_argument("--trigger")
        else:
            for key in ("receipts", "notion", "inbox", "note"):
                p.add_argument(f"--{key}", required=True)
    sub.add_parser("list").add_argument("workflow_id")
    sub.add_parser("doctor"), sub.add_parser("init")
    clear = sub.add_parser("clear")
    clear.add_argument("workflow_id"), clear.add_argument("--env-removed", action="store_true"), clear.add_argument("--pr")
    args = parser.parse_args(argv)
    worker = _worker(args)
    if args.command == "init":
        worker.init()
        print(f"initialised {worker.state}/repo.git from {worker.remote}")
        return 0
    if args.command == "doctor":
        lines = worker.doctor()
        for status, line in lines:
            print(f"{status}: {line}")
        return 1 if any(status == "fail" for status, _ in lines) else 0
    if args.command == "list":
        for kind in record.KINDS:
            for item in worker.list(args.workflow_id, kind)["items"]:
                print(f"{item['completed_at']}  {item['stage']:<9} {item['kind']:<8} {item['proposal_id']}  {(item.get('pr') or {}).get('url', '')}")
        return 0
    if args.command == "clear":
        import workflow_pr_retire as retire
        return retire.clear_command(args.workflow_id, args.env_removed, args.pr, worker.live)
    request = _request(args)
    rec, response = worker.submit(request, cli_actor()) if args.submit else worker.preview(request, cli_actor())
    return _print_stage(rec, response)


if __name__ == "__main__":
    sys.exit(main())
