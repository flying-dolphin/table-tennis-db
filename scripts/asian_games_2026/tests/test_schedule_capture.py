import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.asian_games_2026.schedule_capture import verified_capture
from scripts.asian_games_2026.scrape_schedule import fetch_schedule


class ScheduleCaptureTests(unittest.TestCase):
    def test_complete_capture_hashes_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            days = [{'raw': '2026-09-22'}, {'raw': '2026-09-23'}]
            with patch('scripts.asian_games_2026.scrape_schedule.fetch_json', side_effect=[days, [], []]):
                rows = fetch_schedule(raw_root=root)
            capture = verified_capture(root, rows)
            self.assertTrue(capture['complete'])
            changed = dict(rows, **{'2026-09-22': [{'Key': 'different'}]})
            self.assertIsNone(verified_capture(root, changed))
            with patch('scripts.asian_games_2026.scrape_schedule.fetch_json', side_effect=[days, [], OSError('network')]):
                with self.assertRaises(OSError):
                    fetch_schedule(raw_root=root)
            self.assertIsNone(verified_capture(root, rows))

    def test_malformed_row_cannot_authorize_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('scripts.asian_games_2026.scrape_schedule.fetch_json', side_effect=[
                    [{'raw': '2026-09-22'}], [{'isH2H': True, 'Key': 'broken'}]]):
                with self.assertRaises(ValueError):
                    fetch_schedule(raw_root=root)
            self.assertIsNone(verified_capture(root, {}))
