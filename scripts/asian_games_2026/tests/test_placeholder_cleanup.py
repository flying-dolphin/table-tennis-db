import unittest
from unittest.mock import patch

from scripts.asian_games_2026.tests import test_import_current
from scripts.asian_games_2026.import_current import import_snapshot


class PlaceholderCleanupTests(unittest.TestCase):
    tearDown = test_import_current.ImportCurrentTests.tearDown

    def setUp(self):
        test_import_current.ImportCurrentTests.setUp(self)
        self.empty = dict(external_match_code='WT.empty', sub_event_type_code='WT',
                          stage_code='MAIN_DRAW', round_code='R16',
                          scheduled_local_at='2020-09-22T10:00:00', status='scheduled',
                          source_status='PROVISIONAL', sides=[], rubbers=[])
        self.real = dict(self.empty, external_match_code='WT.real', source_status='OFFICIAL',
                         status='completed', match_score='3-0',
                         sides=[dict(side_no=1, team_code='CHN'), dict(side_no=2, team_code='JPN')])
        import_snapshot(self.conn, {'team_ties': [self.empty]})

    def snapshot(self, batch):
        return dict(team_ties=[self.real], matches=[], schedule_capture=dict(
            complete=True, batch_id=batch, completed_at=f'2026-09-22T00:00:0{batch}Z',
            dates=['2020-09-22'], schedule_keys=['WT.real']))

    def exists(self):
        return self.conn.execute("SELECT count(*) FROM current_event_team_ties WHERE external_match_code='WT.empty'").fetchone()[0]

    def test_two_distinct_batches_and_audit(self):
        first = self.snapshot('1')
        import_snapshot(self.conn, first)
        import_snapshot(self.conn, first)
        self.assertEqual(self.exists(), 1)
        import_snapshot(self.conn, self.snapshot('2'))
        self.assertEqual(self.exists(), 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM asian_games_placeholder_audit').fetchone()[0], 1)

    def test_reappearance_resets_confirmation(self):
        import_snapshot(self.conn, self.snapshot('1'))
        seen = self.snapshot('2')
        seen['team_ties'].append(self.empty)
        import_snapshot(self.conn, seen)
        import_snapshot(self.conn, self.snapshot('3'))
        self.assertEqual(self.exists(), 1)
        import_snapshot(self.conn, self.snapshot('4'))
        self.assertEqual(self.exists(), 0)

    def test_protection_conditions(self):
        for change in ({'status': 'live'}, {'source_status': 'START_LIST'},
                       {'match_score': '0-0'}, {'winner_side': 'A'},
                       {'scheduled_local_at': '2099-09-22T10:00:00'},
                       {'round_code': 'QF'},
                       {'sides': [dict(side_no=1, team_code='CHN')]}):
            with self.subTest(change=change):
                self.conn.execute('DELETE FROM current_event_team_ties')
                self.conn.commit()
                import_snapshot(self.conn, {'team_ties': [dict(self.empty, **change)]})
                for batch in ('1', '2'):
                    import_snapshot(self.conn, self.snapshot(batch))
                self.assertEqual(self.exists(), 1)

    def test_incomplete_or_uncovered_snapshot_does_not_clean(self):
        for metadata in (None, {'complete': False}, dict(complete=True, batch_id='x', dates=[])):
            snap = self.snapshot('1')
            snap['schedule_capture'] = metadata
            import_snapshot(self.conn, snap)
            import_snapshot(self.conn, snap)
            self.assertEqual(self.exists(), 1)

    def test_child_match_prevents_cleanup(self):
        tie_id = self.conn.execute("SELECT current_team_tie_id FROM current_event_team_ties").fetchone()[0]
        self.conn.execute("INSERT INTO current_event_matches(event_id,current_team_tie_id,sub_event_type_code,external_match_code) VALUES (6666,?,'WT','rubber')", (tie_id,))
        self.conn.commit()
        for batch in ('1', '2'):
            import_snapshot(self.conn, self.snapshot(batch))
        self.assertEqual(self.exists(), 1)

    def test_failed_import_rolls_back_cleanup_and_confirmation(self):
        from scripts.asian_games_2026.placeholder_cleanup import cleanup_placeholders
        import_snapshot(self.conn, self.snapshot('1'))
        def fail_after_cleanup(conn, snapshot):
            cleanup_placeholders(conn, snapshot)
            raise RuntimeError('forced failure')
        with patch('scripts.asian_games_2026.import_current.cleanup_placeholders', fail_after_cleanup):
            with self.assertRaises(RuntimeError):
                import_snapshot(self.conn, self.snapshot('2'))
        self.assertEqual(self.exists(), 1)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM asian_games_placeholder_audit').fetchone()[0], 0)
        import_snapshot(self.conn, self.snapshot('2'))
        self.assertEqual(self.exists(), 0)

    def test_failed_capture_between_successes_does_not_advance(self):
        import_snapshot(self.conn, self.snapshot('1'))
        failed = self.snapshot('2')
        failed['schedule_capture']['complete'] = False
        import_snapshot(self.conn, failed)
        self.assertEqual(self.exists(), 1)
        import_snapshot(self.conn, self.snapshot('3'))
        self.assertEqual(self.exists(), 0)

    def test_cached_detail_is_not_official_schedule_evidence(self):
        for batch in ('1', '2'):
            snapshot = self.snapshot(batch)
            snapshot['schedule_capture']['schedule_keys'] = ['unrelated']
            import_snapshot(self.conn, snapshot)
        self.assertEqual(self.exists(), 1)

    def test_older_snapshot_does_not_count_twice(self):
        import_snapshot(self.conn, self.snapshot('2'))
        import_snapshot(self.conn, self.snapshot('1'))
        self.assertEqual(self.exists(), 1)
        import_snapshot(self.conn, self.snapshot('3'))
        self.assertEqual(self.exists(), 0)


if __name__ == '__main__':
    unittest.main()
