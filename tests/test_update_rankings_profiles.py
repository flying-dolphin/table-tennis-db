import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_update_rankings_profiles as pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        for name, value in [('ROOT', self.root), ('STATE_FILE', self.root / 'state.json')]:
            p = patch.object(pipeline, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.args = pipeline.build_parser().parse_args(['--skip-deploy'])

    def fake_scrape(self, cmd):
        self.commands.append(cmd)
        weekly_dir = Path(cmd[cmd.index('--weekly-output-dir') + 1])
        results_dir = Path(cmd[cmd.index('--results-output-dir') + 1])
        weekly_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        for name in ['women_singles_top1000_week41.json', 'women_singles_top1000_week41_with_ids.json']:
            (weekly_dir / name).write_text('{}')
        (results_dir / 'results_women_top1000_new.json').write_text('{}')
        manifest = Path(cmd[cmd.index('--output-manifest') + 1])
        manifest.write_text(json.dumps({
            'weekly_file': str(weekly_dir / 'women_singles_top1000_week41.json'),
            'results_file': str(results_dir / 'results_women_top1000_new.json'),
            'merged_file': str(weekly_dir / 'women_singles_top1000_week41_with_ids.json'),
            'unresolved_file': str(weekly_dir / 'women_singles_top1000_week41_with_ids_unresolved.json'),
        }))
        return 0

    def test_new_run_ignores_shared_old_files_and_profiles_use_same_run(self):
        old = self.root / 'data/rankings/orig'
        old.mkdir(parents=True)
        (old / 'women_singles_top1000_week40.json').write_text('{}')
        self.commands = []
        runners = {stage: (lambda args, state: {}) for stage in pipeline.STAGES}
        runners['scrape_rankings'] = pipeline.stage_scrape_rankings
        runners['scrape_profiles'] = pipeline.stage_scrape_profiles
        with patch.object(pipeline, 'run_cmd', side_effect=self.fake_scrape), patch.dict(pipeline.STAGE_RUNNERS, runners):
            self.assertEqual(pipeline.run(self.args), 0)
        state = json.loads(pipeline.STATE_FILE.read_text())
        self.assertTrue(state.get('run_id'))
        dirs = [cmd[cmd.index('--weekly-output-dir') + 1] for cmd in self.commands]
        self.assertEqual(dirs[0], dirs[1])
        self.assertNotEqual(Path(dirs[0]), old)
        self.assertIn(state['run_id'], dirs[0])
        self.assertIn('week41', state['stages']['scrape_rankings']['meta']['merged_file'])

    def test_retry_keeps_run_directory_and_reset_changes_it(self):
        commands = []
        def fail(cmd):
            commands.append(cmd)
            return 1
        with patch.object(pipeline, 'run_cmd', side_effect=fail):
            self.assertEqual(pipeline.run(self.args), 3)
            self.assertEqual(pipeline.run(self.args), 3)
            self.args.reset = True
            self.assertEqual(pipeline.run(self.args), 3)
        dirs = [c[c.index('--weekly-output-dir') + 1] for c in commands]
        self.assertEqual(dirs[0], dirs[1])
        self.assertNotEqual(dirs[1], dirs[2])

    def test_review_retry_preserves_previous_status(self):
        state = {'stages': {'resolve_ids': {'status': 'needs_review', 'meta': {'report': 'x'}}}}
        pipeline.set_stage(state, 'resolve_ids', pipeline.STATUS_RUNNING)
        self.assertEqual(state['stages']['resolve_ids'].get('previous_status'), 'needs_review')
        self.assertEqual(state['stages']['resolve_ids']['meta'], {'report': 'x'})

    def test_dry_run_does_not_create_state(self):
        self.args.dry_run = True
        self.assertEqual(pipeline.run(self.args), 0)
        self.assertFalse(pipeline.STATE_FILE.exists())

    def test_deploy_passes_exact_translated_ranking(self):
        state = {'since_ts': '2026-10-12 21:00:00', 'stages': {
            'translate_rankings': {'meta': {'cn_file': '/tmp/current.json'}}}}
        with patch.object(pipeline, 'run_cmd', return_value=0) as command:
            pipeline.stage_deploy(self.args, state)
        self.assertIn('--ranking-file', command.call_args.args[0])
        self.assertIn('/tmp/current.json', command.call_args.args[0])

    def test_changed_top_rejected_on_retry(self):
        with patch.object(pipeline, 'run_cmd', return_value=1) as command:
            self.assertEqual(pipeline.run(self.args), 3)
            self.args.top = 50
            self.assertEqual(pipeline.run(self.args), 2)
            self.assertEqual(command.call_count, 1)

    def test_legacy_failed_state_starts_new_run(self):
        pipeline.STATE_FILE.write_text(json.dumps({
            'since_ts': '2026-01-01', 'stages': {'scrape_rankings': {'status': 'failed'}}}))
        with patch.object(pipeline, 'run_cmd', return_value=1):
            self.assertEqual(pipeline.run(self.args), 3)
        state = json.loads(pipeline.STATE_FILE.read_text())
        self.assertTrue(state.get('run_id'))
        self.assertNotEqual(state['since_ts'], '2026-01-01')

    def test_parent_and_child_pass_actual_outputs_without_shared_discovery(self):
        import run_ranking_profile as child
        self.args.top = 1
        self.args.aliases = str(self.root / 'aliases.json')
        Path(self.args.aliases).write_text('[]')
        row = {'rank': 1, 'name': 'TEST Player', 'country_code': 'CHN', 'points': 100}
        def weekly(args):
            Path(args.output_dir, 'women_singles_top1_week41.json').write_text(
                json.dumps({'rankings': [row]}))
            return 0
        def results(args):
            Path(args.output_dir, 'results_women_top1_new.json').write_text(
                json.dumps({'rankings': [{**row, 'player_id': '123'}]}))
            return 0
        def subprocess(cmd):
            return child.run(child.build_parser().parse_args(cmd[2:]))
        runners = {stage: (lambda args, state: {}) for stage in pipeline.STAGES}
        runners['scrape_rankings'] = pipeline.stage_scrape_rankings
        runners['scrape_profiles'] = pipeline.stage_scrape_profiles
        with patch.object(pipeline, 'run_cmd', side_effect=subprocess), \
             patch.dict(pipeline.STAGE_RUNNERS, runners), \
             patch.object(child, 'run_weekly_wp', side_effect=weekly) as scrape, \
             patch.object(child, 'run_results', side_effect=results), \
             patch.object(child, 'is_results_snapshot_usable', return_value=(True, 'ok')):
            self.assertEqual(pipeline.run(self.args), 0)
        self.assertEqual(scrape.call_count, 1)
        state = json.loads(pipeline.STATE_FILE.read_text())
        merged = json.loads(Path(state['stages']['scrape_rankings']['meta']['merged_file']).read_text())
        self.assertEqual(merged['rankings'][0]['player_id'], '123')

    def test_review_retry_remerges_aliases(self):
        weekly = self.root / 'weekly.json'
        results = self.root / 'results.json'
        unresolved = self.root / 'unresolved.json'
        weekly.write_text('{}')
        results.write_text('{}')
        unresolved.write_text(json.dumps({'total_unresolved': 1}))
        state = {'stages': {
            'scrape_rankings': {'meta': {
                'weekly_file': str(weekly), 'results_file': str(results),
                'merged_file': str(self.root / 'merged.json'), 'unresolved_file': str(unresolved)}},
            'resolve_ids': {'status': 'needs_review'}}}
        pipeline.set_stage(state, 'resolve_ids', 'running')
        def merge(cmd):
            self.assertIn('scripts/merge_ranking_ids.py', cmd)
            unresolved.write_text(json.dumps({'total_unresolved': 0}))
            return 0
        with patch.object(pipeline, 'run_cmd', side_effect=merge) as command:
            self.assertEqual(pipeline.stage_resolve_ids(self.args, state), {})
        self.assertEqual(command.call_count, 1)

    def test_success_without_manifest_fails_instead_of_using_old_archive(self):
        state = {'run_id': 'new', 'stages': {}}
        with patch.object(pipeline, 'run_cmd', return_value=0):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.stage_scrape_rankings(self.args, state)


if __name__ == '__main__':
    unittest.main()
