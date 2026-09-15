#!/usr/bin/env python3
"""The git worker behind a Control Room proposal (T5.3b): a dedicated bare clone under the
state root, one detached worktree per proposal, and a push that can only ever name a
`control-room/*` branch. Every argv is built from constants plus a branch that matched
BRANCH_RE; the process-wide git config is never read (GIT_CONFIG_GLOBAL points at the
state root's own file), no hook from the clone ever runs, and nothing here knows how to
force-push, merge, or touch `main`.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import time
from typing import Any, Callable

BRANCH_RE = re.compile(r"^control-room/(schedule|retire)-[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z$")
COMMAND_TIMEOUT_SECONDS = 60
TRANSFER_TIMEOUT_SECONDS = 90
GITCONFIG = """[user]
\tname = {name}
\temail = {email}
[credential "https://github.com"]
\thelper = !/usr/bin/gh auth git-credential
[push]
\tdefault = nothing
[advice]
\tdetachedHead = false
[core]
\thooksPath = /dev/null
"""
CHANGE_BY_STATUS = {"M": "modified", "D": "deleted", "A": "added", "R": "renamed", "C": "added", "T": "modified"}

Runner = Callable[[list[str], pathlib.Path | None, dict[str, str], int], tuple[int, str, str]]


class GitFailed(Exception):
    def __init__(self, message: str, argv: list[str] | None = None, exit_code: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.argv, self.exit_code, self.stderr = argv or [], exit_code, stderr


def subprocess_runner(argv: list[str], cwd: pathlib.Path | None, env: dict[str, str], timeout: int) -> tuple[int, str, str]:
    try:
        done = subprocess.run(argv, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", f"timed out after {timeout}s"
    except OSError as exc:
        return 127, "", str(exc)
    return done.returncode, done.stdout, done.stderr


def split_author(author: str) -> tuple[str, str]:
    match = re.match(r"^\s*(.*?)\s*<([^>]+)>\s*$", author)
    if not match:
        raise GitFailed(f"author must read 'Name <email>', got {author!r}")
    return match.group(1), match.group(2)


class GitRepo:
    def __init__(self, state_root: pathlib.Path | str, remote_url: str, author: str, runner: Runner | None = None) -> None:
        self.state = pathlib.Path(state_root)
        self.repo = self.state / "repo.git"
        self.work = self.state / "work"
        self.gitconfig = self.state / "gitconfig"
        self.remote_url, self.author = remote_url, author
        self.runner = runner or subprocess_runner
        self.commands: list[dict[str, Any]] = []

    def _env(self) -> dict[str, str]:
        passthrough = ("PATH", "HOME", "GH_TOKEN", "GH_CONFIG_DIR", "XDG_CONFIG_HOME")
        env = {key: value for key, value in os.environ.items() if key in passthrough or key.startswith("FAKE_")}
        env.update({"GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                    "LC_ALL": "C", "TZ": "UTC"})
        return env

    def run(self, args: list[str], cwd: pathlib.Path | None = None, timeout: int = COMMAND_TIMEOUT_SECONDS, check: bool = True) -> str:
        argv = ["git", "--no-pager", *args]
        started = time.monotonic()
        code, out, err = self.runner(argv, cwd or self.repo, self._env(), timeout)
        self.commands.append({"argv": ["git", *args], "exit": code, "seconds": round(time.monotonic() - started, 3),
                              "stderr": err.strip()[-2000:]})
        if check and code != 0:
            raise GitFailed(f"git {' '.join(args[:2])} failed ({code}): {err.strip()[-500:]}", argv, code, err)
        return out

    def write_gitconfig(self) -> None:
        name, email = split_author(self.author)
        self.state.mkdir(parents=True, exist_ok=True)
        self.gitconfig.write_text(GITCONFIG.format(name=name, email=email), encoding="utf-8")

    def init(self) -> None:
        self.write_gitconfig()
        self.work.mkdir(parents=True, exist_ok=True)
        if not (self.repo / "HEAD").exists():
            self.run(["clone", "--quiet", "--bare", self.remote_url, str(self.repo)], cwd=self.state, timeout=TRANSFER_TIMEOUT_SECONDS)
        configured = self.run(["remote", "get-url", "origin"]).strip()
        if configured != self.remote_url:
            raise GitFailed(f"repo.git origin is {configured}, not the configured remote {self.remote_url}")

    def fetch_main(self) -> None:
        self.run(["fetch", "--quiet", "origin", "+refs/heads/main:refs/remotes/origin/main"], timeout=TRANSFER_TIMEOUT_SECONDS)

    def base_sha(self) -> str:
        return self.run(["rev-parse", "refs/remotes/origin/main"]).strip()

    def worktree_add(self, pid: str) -> pathlib.Path:
        path = self.work / pid
        self.run(["worktree", "add", "--quiet", "--detach", str(path), "refs/remotes/origin/main"])
        return path

    def worktree_remove(self, pid: str) -> None:
        path = self.work / pid
        shutil.rmtree(path, ignore_errors=True)
        (path.parent / f"{path.name}.commit-msg").unlink(missing_ok=True)
        self.run(["worktree", "prune"], check=False)

    def diff(self, path: pathlib.Path) -> tuple[str, str, list[dict[str, Any]]]:
        self.run(["add", "-A", "-N", "."], cwd=path)
        text = self.run(["diff", "--no-color", "--binary", "-M", "HEAD"], cwd=path)
        stat = self.run(["diff", "--stat", "-M", "HEAD"], cwd=path)
        status = self.run(["diff", "--name-status", "-M", "HEAD"], cwd=path)
        return text, stat, _files(status)

    def commit(self, path: pathlib.Path, branch: str, message: str) -> str:
        self._assert_branch(branch)
        self.run(["switch", "--quiet", "-c", branch], cwd=path)
        self.run(["add", "-A", "."], cwd=path)
        self._commit(path, message)
        return self.run(["rev-parse", "HEAD"], cwd=path).strip()

    def _commit(self, path: pathlib.Path, message: str) -> None:
        message_file = path.parent / f"{path.name}.commit-msg"
        message_file.write_text(message, encoding="utf-8")
        try:
            self.run(["commit", "--quiet", "-F", str(message_file)], cwd=path)
        finally:
            message_file.unlink(missing_ok=True)

    def push_guarded(self, branch: str, cwd: pathlib.Path | None = None) -> None:
        self._assert_branch(branch)
        self.run(["push", "origin", f"HEAD:refs/heads/{branch}"], cwd=cwd, timeout=TRANSFER_TIMEOUT_SECONDS)

    def remote_heads(self, prefix: str) -> list[str]:
        out = self.run(["ls-remote", "--heads", "origin", f"{prefix}*"], timeout=TRANSFER_TIMEOUT_SECONDS)
        return sorted(line.split("\t", 1)[1].removeprefix("refs/heads/") for line in out.splitlines() if "\t" in line)

    def cleanup(self, pid: str, branch: str | None = None) -> None:
        self.worktree_remove(pid)
        if branch and BRANCH_RE.match(branch):
            self.run(["branch", "-D", branch], check=False)

    @staticmethod
    def _assert_branch(branch: str) -> None:
        if not BRANCH_RE.match(branch or ""):
            raise GitFailed(f"refusing to name {branch!r}: not a control-room/<kind>-<id>-<stamp> branch")


def _files(status: str) -> list[dict[str, Any]]:
    files = []
    for line in status.splitlines():
        cells = line.split("\t")
        if len(cells) < 2:
            continue
        code = cells[0][:1]
        entry: dict[str, Any] = {"path": cells[-1], "change": CHANGE_BY_STATUS.get(code, "modified"), "from": None}
        if code in ("R", "C") and len(cells) == 3:
            entry["from"] = cells[1]
        files.append(entry)
    return sorted(files, key=lambda f: f["path"])
