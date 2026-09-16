#!/usr/bin/env python3
"""Serve the real bin/control_broker.py on a unix socket, unprivileged, against the shims.

Helper, not a suite. Each connection spawns `python3 bin/control_broker.py --serve` with the
connection as stdin/stdout — the same contract as `control-room-broker.socket` (Accept=yes) —
so the screen side and the loopback smoke exercise the socket path without root or a unit.

    serve(socket_path, env, argv)            # blocks; run it in a thread and call shutdown()
    make_server(socket_path, env, argv)      # the ThreadingUnixStreamServer, not yet serving
    sandbox(receipts, now=None)              # (env, argv) for the fixture shims in a temp dir

CLI (the smoke):  fake_broker_socket.py --socket /tmp/crb.sock --fixture-env [--receipts DIR]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import socketserver
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BROKER = ROOT / "bin" / "control_broker.py"


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        fd = self.request.fileno()
        subprocess.run(self.server.argv, stdin=fd, stdout=fd, env=self.server.env, check=False)


class BrokerSocketServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, env: dict[str, str], argv: list[str]) -> None:
        self.env, self.argv = env, argv
        path = pathlib.Path(socket_path)
        if path.exists():
            path.unlink()
        super().__init__(str(path), _Handler)


def make_server(socket_path: str, env: dict[str, str], argv: list[str]) -> BrokerSocketServer:
    return BrokerSocketServer(socket_path, env, argv)


def serve(socket_path: str, env: dict[str, str], argv: list[str]) -> None:
    with make_server(socket_path, env, argv) as server:
        server.serve_forever()


def sandbox(receipts: pathlib.Path, now: str | None = None, root: pathlib.Path | None = None) -> tuple[dict[str, str], list[str]]:
    root = root or pathlib.Path(tempfile.mkdtemp(prefix="control-broker-"))
    if not (root / "bin").exists():
        shutil.copytree(HERE / "bin", root / "bin")
        shutil.copy(HERE / "state.json", root / "state.json")
        shutil.copy(HERE / "calendar.json", root / "calendar.json")
    for sub in ("stamps", "ustamps"):
        (root / sub).mkdir(exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    env = {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(root)}
    argv = [sys.executable, str(BROKER), "--allowlist", str(HERE / "allowlist.json"), "--receipts", str(receipts),
            "--system-stamp-dir", str(root / "stamps"), "--user-stamp-dir", str(root / "ustamps"),
            "--lock", str(root / "lock"), "--peer-uids", str(os.getuid()), "--start-settle", "0"]
    if now:
        argv += ["--now", now]
    return env, argv + ["--serve"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--fixture-env", action="store_true", help="serve the broker against the fixture shims")
    parser.add_argument("--receipts", default="/tmp/crb-receipts")
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)
    if not args.fixture_env:
        parser.error("--fixture-env is the only mode; nothing here ever talks to the real systemd")
    env, broker_argv = sandbox(pathlib.Path(args.receipts), args.now)
    print(f"serving {BROKER} on {args.socket} against the fixture shims; receipts under {args.receipts}", flush=True)
    try:
        serve(args.socket, env, broker_argv)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
