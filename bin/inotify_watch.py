#!/usr/bin/env python3
"""inotify through ctypes, for the board reactor: there is no inotify library on the box.

inotify is not recursive, so the caller names every directory: the cards root (a new card), each
card directory (its ledger), the decisions directory, and the run-receipt directories (a slot
freed). `sync()` reconciles the watch set with the directories that exist now. `wait(timeout)`
returns True when anything changed and False on timeout; the reactor never reads the events'
contents, because it reconciles the whole state on every wake. ENOSPC from inotify_add_watch is
the watch limit, raised as WatchLimit so the reactor can class it `permanent` (`inotify-limit`).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import pathlib
import select
from typing import Iterable

IN_MODIFY = 0x002
IN_ATTRIB = 0x004
IN_CLOSE_WRITE = 0x008
IN_MOVED_FROM = 0x040
IN_MOVED_TO = 0x080
IN_CREATE = 0x100
IN_DELETE = 0x200
IN_DELETE_SELF = 0x400
IN_MOVE_SELF = 0x800
IN_ONLYDIR = 0x01000000
IN_NONBLOCK = os.O_NONBLOCK
IN_CLOEXEC = os.O_CLOEXEC
MASK = (IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE | IN_DELETE
        | IN_DELETE_SELF | IN_MOVE_SELF | IN_ONLYDIR)

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
_libc.inotify_init1.argtypes = [ctypes.c_int]
_libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
_libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]


class WatchLimit(OSError):
    """The kernel's per-user watch limit is spent (fs.inotify.max_user_watches)."""


class Watcher:
    def __init__(self) -> None:
        fd = _libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        self.fd = fd
        self.watches: dict[pathlib.Path, int] = {}

    def add(self, path: pathlib.Path) -> bool:
        wd = _libc.inotify_add_watch(self.fd, os.fsencode(path), MASK)
        if wd >= 0:
            self.watches[path] = wd
            return True
        code = ctypes.get_errno()
        if code == errno.ENOSPC:
            raise WatchLimit(code, f"inotify watch limit reached at {path}")
        if code in (errno.ENOENT, errno.ENOTDIR):
            return False
        raise OSError(code, f"inotify_add_watch {path}")

    def sync(self, paths: Iterable[pathlib.Path]) -> None:
        wanted = {pathlib.Path(p) for p in paths}
        for path in [p for p in self.watches if p not in wanted or not p.is_dir()]:
            _libc.inotify_rm_watch(self.fd, self.watches.pop(path))
        for path in sorted(wanted - self.watches.keys()):
            self.add(path)

    def wait(self, timeout: float | None) -> bool:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return False
        self._drain()
        return True

    def _drain(self) -> None:
        while True:
            try:
                if not os.read(self.fd, 65536):
                    return
            except BlockingIOError:
                return

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self) -> "Watcher":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
