#!/usr/bin/env python3
"""bin/inotify_watch.py against a real kernel: one watch per directory, not recursive."""
from __future__ import annotations

import errno
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inotify_watch", ROOT / "bin" / "inotify_watch.py")
inotify_watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inotify_watch)


class Watch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.cards = self.root / "cards"
        (self.cards / "alpha").mkdir(parents=True)
        self.watcher = inotify_watch.Watcher()

    def tearDown(self):
        self.watcher.close()
        self.tmp.cleanup()

    def test_quiet_times_out(self):
        self.watcher.sync([self.cards])
        self.assertFalse(self.watcher.wait(0.05))

    def test_a_new_card_dir_wakes_the_cards_watch(self):
        self.watcher.sync([self.cards])
        (self.cards / "beta").mkdir()
        self.assertTrue(self.watcher.wait(1))

    def test_a_ledger_append_wakes_its_card_watch(self):
        self.watcher.sync([self.cards, self.cards / "alpha"])
        with (self.cards / "alpha" / "events.jsonl").open("a") as handle:
            handle.write("{}\n")
        self.assertTrue(self.watcher.wait(1))

    def test_not_recursive_without_the_card_watch(self):
        self.watcher.sync([self.cards])
        (self.cards / "alpha" / "events.jsonl").write_text("{}\n")
        self.assertFalse(self.watcher.wait(0.1))

    def test_one_wake_drains_every_pending_event(self):
        self.watcher.sync([self.cards])
        for name in ("b", "c", "d"):
            (self.cards / name).mkdir()
        self.assertTrue(self.watcher.wait(1))
        self.assertFalse(self.watcher.wait(0.05))

    def test_sync_drops_a_vanished_dir_and_skips_a_missing_one(self):
        self.watcher.sync([self.cards, self.cards / "alpha", self.root / "absent"])
        self.assertEqual(set(self.watcher.watches), {self.cards, self.cards / "alpha"})
        (self.cards / "alpha").rmdir()
        self.watcher.wait(0.1)
        self.watcher.sync([self.cards, self.cards / "alpha"])
        self.assertEqual(set(self.watcher.watches), {self.cards})

    def test_the_watch_limit_is_its_own_error(self):
        with mock.patch.object(inotify_watch._libc, "inotify_add_watch", return_value=-1), \
                mock.patch.object(inotify_watch.ctypes, "get_errno", return_value=errno.ENOSPC):
            with self.assertRaises(inotify_watch.WatchLimit):
                self.watcher.add(self.cards)


if __name__ == "__main__":
    unittest.main()
