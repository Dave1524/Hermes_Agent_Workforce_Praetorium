#!/usr/bin/env python3
"""Run the unchanged verification gate and distinguish drift from other failures.

The gate's parent-shell trace records every fail=1 assignment. A non-drift failure
must remain fatal even when it emits no FAIL/PROBLEM line (shellcheck, for example).
The raw exit code and red lines are never rewritten.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def other_checks_exit(trace: str, exit_code: int) -> int:
    # The sourced gate is one level below the launcher; ignore substitutions and traps
    # inside functions at deeper levels. Accept the direct form for saved old traces too.
    prefix = "++ " if "+ source bin/verify.sh" in trace.splitlines() else "+ "
    commands = [line[len(prefix):] for line in trace.splitlines() if line.startswith(prefix)]
    exits = [i for i, command in enumerate(commands) if command.startswith("exit ")]
    if not exits or commands[exits[-1]] != f"exit {exit_code}":
        return 1
    # verify.sh's EXIT trap removes its temp tree after the exit command is traced.
    commands = commands[:exits[-1]]
    if "fail=0" not in commands:
        return 1
    failures = [i for i, command in enumerate(commands) if command == "fail=1"]
    if exit_code not in (0, 1) or bool(failures) != bool(exit_code):
        return 1
    return int(any(i == 0 or commands[i - 1] != "bash bin/check_deploy_drift.sh" for i in failures))


def run(repo: Path, output: Path) -> dict:
    with tempfile.TemporaryFile() as trace, output.open("wb") as log:
        env = dict(os.environ)
        env.pop("BASH_XTRACEFD", None)
        # Keep trace controls in this shell. Exporting the descriptor number leaks it to
        # test subprocesses that close that fd and can change their stderr or behavior.
        launcher = 'BASH_XTRACEFD=$1; export -n BASH_XTRACEFD; PS4="+ "; set -x; source bin/verify.sh'
        done = subprocess.run(["bash", "-c", launcher, "bin/verify.sh", str(trace.fileno())], cwd=repo, env=env,
                              stdout=log, stderr=subprocess.STDOUT, pass_fds=(trace.fileno(),))
        trace.seek(0)
        other = other_checks_exit(trace.read().decode("utf-8", errors="replace"), done.returncode)
    reds = [line for line in output.read_text(errors="replace").splitlines()
            if re.match(r"\s*FAIL:|PROBLEM\t|\s*DRIFT ", line)]
    return {"verifyExit": done.returncode, "allRed": reds, "otherChecksExit": other}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.repo, args.output)
    print(json.dumps(result))
    return result["verifyExit"] or result["otherChecksExit"]


if __name__ == "__main__":
    raise SystemExit(main())
