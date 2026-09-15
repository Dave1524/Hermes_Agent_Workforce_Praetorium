#!/usr/bin/env python3
"""The check bundle a proposal runs on its own branch before a PR exists (T5.3b). Each check
is `{"id", "class": hard|pinned|info, "status": pass|fail|warn|skip|info, "output"}`; hard
fails block submit, pinned fails block unless acknowledged (then the PR opens as a draft),
info never blocks. Suite-running checks go through an injectable runner so a suite can fake
them; `systemd-analyze` runs for real, with whatever is first on PATH.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_pr_schedule as schedule  # noqa: E402

JOIN_SUITES = ("tests/test_fleet_ownership.sh", "tests/test_workflow_coverage.sh", "tests/test_manifest_surfaces.sh",
               "tests/test_contract_schema.sh")
PRODUCER_SUITE = "tests/test_buzz_unit_wiring.sh"
SUITE_TIMEOUT_SECONDS = 120
# Set in every suite's environment. A suite that itself previews a proposal (the realism test
# in tests/test_control_room_proposals.py) names a workflow slug, so pinned-tests would pin it
# and it would preview again inside itself without end; it skips that test under the marker.
NESTED_MARKER = "WORKFLOW_PR_NESTED"
PASSTHROUGH_ENV = ("PATH", "HOME", "AGENT_WORKFORCE_RUNTIME", "FAKE_CALENDAR", "FAKE_SYSTEMCTL_STATE", "FAKE_SYSTEMCTL_LOG",
                   "FAKE_GH_LOG", "FAKE_GH_PR_LIST", "FAKE_GH_FAIL")
Runner = Callable[[list[str], pathlib.Path, dict[str, str], int], tuple[int, str, str]]


def subprocess_runner(argv: list[str], cwd: pathlib.Path, env: dict[str, str], timeout: int) -> tuple[int, str, str]:
    # A suite is its own process group so a timeout kills the whole tree: subprocess.run's
    # timeout kills only the direct child and orphans everything it spawned.
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
    except OSError as exc:
        return 127, "", str(exc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, _ = proc.communicate()
        return 124, out or "", f"timed out after {timeout}s"
    return proc.returncode, out, err


def _kill_group(proc: subprocess.Popen) -> None:
    import signal
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def check_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in PASSTHROUGH_ENV if key in os.environ}
    env.update({key: value for key, value in os.environ.items() if key.startswith("DRIFT_")})
    env.update({"LC_ALL": "C", "TZ": "UTC", NESTED_MARKER: "1"})
    return env


def _result(check_id: str, klass: str, status: str, output: str) -> dict[str, Any]:
    return {"id": check_id, "class": klass, "status": status, "output": output.rstrip()}


def _fail_lines(output: str) -> str:
    lines = [line for line in output.splitlines() if "FAIL" in line or line.startswith("Traceback") or "Error" in line]
    return "\n".join(lines[:40]) or output.strip()[-2000:]


def schedule_parses(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    outputs, failed = [], False
    for spec in ctx.get("specs", []):
        try:
            elapses = schedule.systemd_analyze_calendar(spec)
            outputs.append(f"{spec}: " + "; ".join(f"{e['local']} = {e['utc']}" for e in elapses))
        except (ValueError, OSError) as exc:
            failed = True
            outputs.append(f"{spec}: {exc}")
    return _result("schedule-parses", "hard", "fail" if failed else "pass", "\n".join(outputs))


def unit_verify(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    timer = pathlib.Path(worktree) / ctx["timer_path"]
    try:
        done = subprocess.run(["systemd-analyze", "verify", str(timer)], capture_output=True, text=True, timeout=60,
                              env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _result("unit-verify", "hard", "fail", f"systemd-analyze verify: {exc}")
    name = timer.name
    lines = [line for line in (done.stdout + done.stderr).splitlines() if name in line or str(timer) in line]
    failed = done.returncode != 0 or any("bad unit file setting" in line for line in lines)
    return _result("unit-verify", "hard", "fail" if failed else "pass", "\n".join(lines) or f"{name}: verified")


def schedule_collisions(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    found = schedule.collisions(worktree, ctx["unit"], ctx.get("scope", "system"), ctx.get("specs", []), ctx["calendar_runner"])
    return _result("schedule-collisions", "info", "warn" if found else "pass", "\n".join(found) or "no other timer elapses within 30 min")


def _run_suites(check_id: str, klass: str, worktree: pathlib.Path, suites: list[str], runner: Runner) -> dict[str, Any]:
    present = [s for s in suites if (pathlib.Path(worktree) / s).is_file()]
    if not present:
        return _result(check_id, klass, "skip", "none of " + ", ".join(suites) + " is in this checkout")
    failures, outputs = [], []
    for suite in present:
        code, out, err = runner(["bash", suite], pathlib.Path(worktree), check_env(), SUITE_TIMEOUT_SECONDS)
        if code != 0:
            failures.append(f"{suite} (exit {code}):\n{_fail_lines(out + err)}")
        else:
            outputs.append(f"{suite}: pass")
    return _result(check_id, klass, "fail" if failures else "pass", "\n".join(failures + outputs))


def manifest_joins(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    return _run_suites("manifest-joins", "hard", worktree, list(JOIN_SUITES), runner)


def producer_join(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    return _run_suites("producer-join", "hard", worktree, [PRODUCER_SUITE], runner)


def find_pinned_suites(worktree: pathlib.Path, tokens: list[str], deleted: list[str]) -> list[str]:
    worktree = pathlib.Path(worktree)
    pattern = re.compile("|".join(rf"(?<![A-Za-z0-9-]){re.escape(t)}(?![A-Za-z0-9-])" for t in tokens if t)) if tokens else None
    found = []
    for path in sorted(worktree.glob("tests/test_*.sh")):
        relative = str(path.relative_to(worktree))
        if relative in deleted or pattern is None:
            continue
        companion = path.with_suffix(".py")
        texts = [relative, _read(path)] + ([_read(companion)] if companion.is_file() else [])
        if any(pattern.search(text) for text in texts):
            found.append(relative)
    return found


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def pinned_tests(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    suites = find_pinned_suites(worktree, ctx.get("slugs", []), ctx.get("deleted", []))
    suites += [extra for extra in ctx.get("pinned_extra", []) if extra not in suites and (pathlib.Path(worktree) / extra).is_file()]
    if not suites:
        return _result("pinned-tests", "pinned", "pass", "no suite in tests/ names " + ", ".join(ctx.get("slugs", [])))
    failures, passes = [], []
    for suite in suites:
        code, out, err = runner(["bash", suite], pathlib.Path(worktree), check_env(), SUITE_TIMEOUT_SECONDS)
        names = suite + (f" + {suite[:-3]}.py" if (pathlib.Path(worktree) / (suite[:-3] + ".py")).is_file() else "")
        if code != 0:
            failures.append(f"{names} (exit {code}):\n{_fail_lines(out + err)}")
        else:
            passes.append(f"{names}: pass")
    return _result("pinned-tests", "pinned", "fail" if failures else "pass", "\n".join(failures + passes))


def residue_source(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    import workflow_retire_residue as residue
    report = residue.scan_source(worktree, ctx["subjects"])
    blocking = [item for item in report["items"] if item["blocks"]]
    output = residue.render_w19_table(report) if report["items"] else "no residue"
    if blocking:
        output = "blocking: " + ", ".join(f"{item['path']} ({item['class']})" for item in blocking) + "\n" + output
    return _result("residue-source", "hard", "fail" if blocking else "pass", output)


def drift_introduced(base_output: str, branch_output: str) -> list[str]:
    base = set(line.strip() for line in base_output.splitlines() if line.strip().startswith(("DRIFT", "info:")))
    return [line.strip() for line in branch_output.splitlines() if line.strip().startswith(("DRIFT", "info:")) and line.strip() not in base]


def drift_preview(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    script = pathlib.Path(worktree) / "bin" / "check_deploy_drift.sh"
    base = ctx.get("base_worktree")
    if not script.is_file() or not base or not (pathlib.Path(base) / "bin" / "check_deploy_drift.sh").is_file():
        return _result("drift-preview", "info", "skip", "bin/check_deploy_drift.sh or the base worktree is not available")
    _, base_out, base_err = runner(["bash", "bin/check_deploy_drift.sh"], pathlib.Path(base), check_env(), SUITE_TIMEOUT_SECONDS)
    _, out, err = runner(["bash", "bin/check_deploy_drift.sh"], pathlib.Path(worktree), check_env(), SUITE_TIMEOUT_SECONDS)
    if any(line.startswith("SKIP: ") for line in (out + err).splitlines()):
        return _result("drift-preview", "info", "skip", (out + err).strip()[-1000:] or "drift check skipped")
    introduced = drift_introduced(base_out + base_err, out + err)
    return _result("drift-preview", "info", "info", "\n".join(introduced) or "this branch introduces no drift finding beyond the base")


def deploy_preview(worktree: pathlib.Path, ctx: dict[str, Any], runner: Runner) -> dict[str, Any]:
    script = pathlib.Path(worktree) / "bin" / "deploy"
    runtime = ctx.get("runtime_root") or os.path.expanduser("~/agent-workforce")
    if not script.is_file():
        return _result("deploy-preview", "info", "skip", "bin/deploy is not in this checkout")
    if not pathlib.Path(runtime).is_dir():
        return _result("deploy-preview", "info", "skip", f"runtime tree {runtime} absent")
    argv = ["bash", "bin/deploy", "--dry-run"] + (["--prune"] if ctx["kind"] == "retire" else [])
    code, out, err = runner(argv, pathlib.Path(worktree), check_env(), SUITE_TIMEOUT_SECONDS)
    items = [line for line in out.splitlines() if line.startswith("  [")]
    if ctx["kind"] != "retire":
        return _result("deploy-preview", "info", "info" if code == 0 else "warn", "\n".join(items) or out.strip()[-1000:])
    subject_paths = set(ctx.get("subject_paths", []))
    mine, also = [], []
    for line in items:
        target = line.split()[-1] if line.split() else ""
        tree = line.split("]")[0].strip("[ ").strip() if "]" in line else ""
        (mine if f"{tree}/{target}" in subject_paths or target in subject_paths else also).append(line)
    output = ["this workflow:"] + (mine or ["  (nothing)"]) + ["also deleted by --prune (deferred exclusions):"] + (also or ["  (nothing)"])
    return _result("deploy-preview", "info", "info" if code == 0 else "warn", "\n".join(output))


CHECKS: tuple[tuple[str, str, Callable[..., dict[str, Any]]], ...] = (
    ("schedule-parses", "schedule", schedule_parses),
    ("unit-verify", "schedule", unit_verify),
    ("schedule-collisions", "schedule", schedule_collisions),
    ("manifest-joins", "both", manifest_joins),
    ("producer-join", "retire", producer_join),
    ("pinned-tests", "both", pinned_tests),
    ("residue-source", "retire", residue_source),
    ("drift-preview", "both", drift_preview),
    ("deploy-preview", "both", deploy_preview),
)


def run_checks(worktree: pathlib.Path, kind: str, ctx: dict[str, Any], runner: Runner | None = None) -> list[dict[str, Any]]:
    runner = runner or subprocess_runner
    results = []
    for check_id, applies, function in CHECKS:
        if applies in (kind, "both"):
            try:
                results.append(function(pathlib.Path(worktree), ctx, runner))
            except Exception as exc:  # a check that crashes is a failed check, never a skipped one
                klass = "info" if check_id in ("schedule-collisions", "drift-preview", "deploy-preview") else "hard"
                results.append(_result(check_id, klass, "warn" if klass == "info" else "fail", f"{type(exc).__name__}: {exc}"))
    return results


def submit_allowed(results: list[dict[str, Any]], kind: str, acknowledge_pinned: bool) -> tuple[bool, list[str]]:
    blockers = []
    for check in results:
        if check["class"] == "hard" and check["status"] == "fail":
            prefix = "residue_in_branch" if check["id"] == "residue-source" else "checks_failed"
            blockers.append(f"{prefix}: {check['id']} — {check['output'].splitlines()[0] if check['output'] else 'failed'}")
        if check["class"] == "pinned" and check["status"] == "fail" and not acknowledge_pinned:
            blockers.append(f"checks_failed: {check['id']} — " + "; ".join(
                line.split(" (exit")[0] for line in check["output"].splitlines() if "(exit" in line) + " (acknowledge_pinned_tests opens a draft)")
    if kind == "retire" and not any(c["id"] == "residue-source" and c["status"] == "pass" for c in results):
        if not any("residue-source" in b for b in blockers):
            blockers.append("residue_in_branch: residue-source did not pass")
    return not blockers, blockers


def draft_required(results: list[dict[str, Any]], acknowledge_pinned: bool) -> bool:
    return acknowledge_pinned and any(c["class"] == "pinned" and c["status"] == "fail" for c in results)
