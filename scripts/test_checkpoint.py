#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.checkpoint import CheckpointStore


class CheckpointStoreTests(unittest.TestCase):
    def test_mark_failed_clears_completed_for_same_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint = CheckpointStore(Path(tmpdir) / "checkpoint.json")
            key = "profile|women|player:114726|scrape"

            checkpoint.mark_done(key, meta={"orig_path": "player_114726.json"})
            checkpoint.mark_failed(key, "Timeout 10000ms exceeded.")

            self.assertFalse(checkpoint.is_done(key))
            self.assertIn(key, checkpoint.data["failed"])


if __name__ == "__main__":
    unittest.main()
