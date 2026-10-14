#!/usr/bin/env python3
"""sd_notify(3) over $NOTIFY_SOCKET with the stdlib: READY=1, WATCHDOG=1, STATUS=….

No socket in the environment (a test, or `--once` under a oneshot) makes every call a no-op that
returns False. An abstract socket is spelled `@name` in the variable and `\\0name` on the wire.
"""
from __future__ import annotations

import os
import socket
from typing import Mapping


def _address(env: Mapping[str, str]) -> str | None:
    path = env.get("NOTIFY_SOCKET")
    if not path:
        return None
    return "\0" + path[1:] if path.startswith("@") else path


def notify(message: str, env: Mapping[str, str] | None = None) -> bool:
    address = _address(os.environ if env is None else env)
    if address is None:
        return False
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC) as sock:
        sock.sendto(message.encode(), address)
    return True


def watchdog_interval(env: Mapping[str, str] | None = None) -> float | None:
    """Seconds between WATCHDOG=1 pings: a third of WatchdogSec, or None when no watchdog is armed."""
    env = os.environ if env is None else env
    usec, pid = env.get("WATCHDOG_USEC"), env.get("WATCHDOG_PID")
    if not usec or not usec.isdigit() or (pid and pid != str(os.getpid())):
        return None
    return int(usec) / 3_000_000


def ready(status: str, env: Mapping[str, str] | None = None) -> bool:
    return notify(f"READY=1\nSTATUS={status}", env)


def ping(status: str | None = None, env: Mapping[str, str] | None = None) -> bool:
    return notify("WATCHDOG=1" + (f"\nSTATUS={status}" if status else ""), env)
