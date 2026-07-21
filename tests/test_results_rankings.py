import sys
import json
import sqlite3
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.checkpoint import CheckpointStore
from lib.anti_bot import RiskControlTriggered
from scrape_results_rankings import (
    add_risk_cooldown_meta,
    build_results_resume_url,
    build_results_checkpoint_meta,
    click_results_page_offset,
    build_output_payload,
    extract_results_reported_total,
    extract_results_page_urls,
    find_completed_results_output,
    find_resumable_results_output,
    find_db_profile_candidates,
    is_results_snapshot_complete,
    parse_results_ranking_html,
    plan_missing_results_page_offsets,
    recover_missing_players_from_db,
    recover_missing_profiles_with_browser,
    recover_missing_results_pages,
    results_resume_wait_seconds,
    scrape_results_rankings,
    select_results_display_100,
    validate_partial_results_snapshot,
    validate_live_page_against_partial,
    validate_scraped_results_count,
)


class ParseResultsRankingHtmlTests(unittest.TestCase):
    def test_extracts_player_id_country_code_and_profile_url_from_ranking_table(self):
        html = """
        <table id="list_58_com_fabrik_58">
          <tbody>
            <tr class="fabrik_row">
              <td></td><td>1</td><td></td><td>9875</td>
              <td><a href="../index.php/player-profile/list/60?resetfilters=1&amp;vw_profiles___player_id_raw=131163&amp;vw_profiles___Name_raw=SUN Yingsha">SUN Yingsha</a></td>
              <td><img title="CHN" src="/images/stories/flags/CHN.png"></td>
              <td>CHINA</td><td>ASIA</td>
            </tr>
          </tbody>
        </table>
        """

        rows = parse_results_ranking_html(html, top_n=10)

        self.assertEqual(
            rows,
            [
                {
                    "rank": 1,
                    "name": "SUN Yingsha",
                    "english_name": "SUN Yingsha",
                    "points": 9875,
                    "country": "CHINA",
                    "country_code": "CHN",
                    "continent": "ASIA",
                    "player_id": "131163",
                    "profile_url": "https://results.ittf.link/index.php/player-profile/list/60?resetfilters=1&vw_profiles___player_id_raw=131163&vw_profiles___Name_raw=SUN Yingsha",
                }
            ],
        )

    def test_falls_back_to_embedded_fabrik_json_when_dom_rows_are_missing(self):
        html = """
        <script>
        {"data":{"fab_rank_ws___Num":2,"fab_rank_ws___Position_raw":2,
        "fab_rank_ws___Points_raw":8865,
        "fab_rank_ws___Name":"<a href='..\\/index.php\\/player-profile\\/list\\/60?resetfilters=1&vw_profiles___player_id_raw=121411&vw_profiles___Name_raw=WANG Manyu'>WANG Manyu<\\/a>",
        "fab_rank_ws___Name_raw":"WANG Manyu",
        "fab_rank_ws___Flag":"<img title='CHN'>",
        "fab_rank_ws___Country_raw":"CHN",
        "fab_rank_ws___Country":"CHINA",
        "fab_rank_ws___ITTF_raw":"ASIA",
        "fab_rank_ws___PID_raw":121411}}
        </script>
        """

        rows = parse_results_ranking_html(html, top_n=10)

        self.assertEqual(rows[0]["rank"], 2)
        self.assertEqual(rows[0]["name"], "WANG Manyu")
        self.assertEqual(rows[0]["country_code"], "CHN")
        self.assertEqual(rows[0]["player_id"], "121411")


class ResultsDisplaySizeTests(unittest.TestCase):
    @staticmethod
    def _ranking_html(row_count: int, total_pages: int = 10, total: int = 958) -> str:
        rows = "".join(
            f"""
            <tr><td></td><td>{rank}</td><td></td><td>1</td>
              <td><a href="/profile?vw_profiles___player_id_raw={100000 + rank}">Player {rank}</a></td>
              <td><img title="AAA"></td><td>AAA</td><td>EUROPE</td>
            </tr>
            """
            for rank in range(1, row_count + 1)
        )
        return (
            f'<div class="list-footer">Page 1 of {total_pages} Total: {total}</div>'
            f'<table id="list_58_com_fabrik_58"><tbody>{rows}</tbody></table>'
        )

    def test_selects_display_100_and_verifies_rows_and_pagination(self):
        page = MagicMock()
        locator = MagicMock()
        locator.count.return_value = 1
        locator.is_visible.return_value = True
        locator.input_value.side_effect = ["25", "100"]
        page.locator.return_value.first = locator
        page.content.return_value = self._ranking_html(100)

        selected = select_results_display_100(page, timeout_sec=0.1, poll_sec=0)

        self.assertTrue(selected)
        locator.select_option.assert_called_once_with("100")

    def test_rejects_display_100_when_page_still_contains_25_rows(self):
        page = MagicMock()
        locator = MagicMock()
        locator.count.return_value = 1
        locator.is_visible.return_value = True
        locator.input_value.return_value = "100"
        page.locator.return_value.first = locator
        page.content.return_value = self._ranking_html(25, total_pages=39)

        selected = select_results_display_100(page, timeout_sec=0, poll_sec=0)

        self.assertFalse(selected)

    def test_verifies_display_100_while_browser_is_on_last_page(self):
        page = MagicMock()
        locator = MagicMock()
        locator.count.return_value = 1
        locator.is_visible.return_value = True
        locator.input_value.return_value = "100"
        page.locator.return_value.first = locator
        page.content.return_value = self._ranking_html(58, total_pages=10).replace(
            "Page 1 of 10 Total: 958",
            "Page 10 of 10 Total: 958",
        )

        selected = select_results_display_100(page, timeout_sec=0, poll_sec=0)

        self.assertTrue(selected)


class ResultsTargetPagePlannerTests(unittest.TestCase):
    @staticmethod
    def _weekly_row(index: int, rank: int | None = None) -> dict:
        return {
            "rank": rank if rank is not None else index + 1,
            "name": f"Player {index + 1}",
            "country_code": "AAA",
            "points": 1000 - index,
        }

    @classmethod
    def _results_row(cls, index: int, rank: int | None = None) -> dict:
        weekly = cls._weekly_row(index, rank)
        player_id = str(100000 + index)
        return {
            **weekly,
            "english_name": weekly["name"],
            "player_id": player_id,
            "profile_url": (
                "https://results.ittf.link/profile?"
                f"vw_profiles___player_id_raw={player_id}"
            ),
        }

    def test_plans_only_pages_containing_scattered_missing_players(self):
        weekly = [self._weekly_row(index) for index in range(350)]
        missing_indexes = {37, 148, 249}
        existing = [
            self._results_row(index)
            for index in range(350)
            if index not in missing_indexes
        ]

        offsets = plan_missing_results_page_offsets(
            weekly,
            existing,
            page_size=100,
            reported_total=350,
        )

        self.assertEqual(offsets, [0, 100, 200])

    def test_uses_weekly_list_index_instead_of_tied_rank_for_page(self):
        weekly = [self._weekly_row(index) for index in range(201)]
        weekly[99]["rank"] = 100
        weekly[100]["rank"] = 100
        existing = [
            self._results_row(index, rank=weekly[index]["rank"])
            for index in range(201)
            if index != 100
        ]

        offsets = plan_missing_results_page_offsets(
            weekly,
            existing,
            page_size=100,
            reported_total=201,
        )

        self.assertEqual(offsets, [100])

    def test_extracts_all_display_100_page_urls_from_footer(self):
        html = """
        <nav><ul class="pagination">
          <li><a title="1" href="/ranking">1</a></li>
          <li><a title="2" href="/ranking/list/58?limitstart58=100">2</a></li>
          <li><a title="3" href="/ranking/list/58?limitstart58=200">3</a></li>
          <li><a title="End" href="/ranking/list/58?limitstart58=900">End</a></li>
        </ul></nav>
        """

        urls = extract_results_page_urls(
            html,
            "https://results.ittf.link/ranking",
        )

        self.assertEqual(urls[0], "https://results.ittf.link/ranking")
        self.assertEqual(urls[100], "https://results.ittf.link/ranking/list/58?limitstart58=100")
        self.assertEqual(urls[200], "https://results.ittf.link/ranking/list/58?limitstart58=200")
        self.assertEqual(urls[900], "https://results.ittf.link/ranking/list/58?limitstart58=900")

    def test_validates_current_page_against_matching_snapshot_offset(self):
        saved = [self._results_row(index) for index in range(900)]
        live_page_nine = [self._results_row(index) for index in range(800, 900)]

        matches, reason = validate_live_page_against_partial(
            live_page_nine,
            saved,
            current_page=9,
            page_size=100,
        )

        self.assertTrue(matches, reason)

    def test_reports_when_current_page_has_no_snapshot_overlap(self):
        saved = [self._results_row(index) for index in range(900)]
        live_page_ten = [self._results_row(index) for index in range(900, 958)]

        matches, reason = validate_live_page_against_partial(
            live_page_ten,
            saved,
            current_page=10,
            page_size=100,
        )

        self.assertIsNone(matches)
        self.assertIn("no overlap", reason)

    def test_clicks_real_pagination_link_for_target_offset(self):
        page = MagicMock()
        page.url = "https://results.ittf.link/ranking"
        links = MagicMock()
        first = MagicMock()
        first.get_attribute.return_value = "/ranking/list/58?limitstart58=800"
        first.is_visible.return_value = True
        second = MagicMock()
        second.get_attribute.return_value = "/ranking/list/58?limitstart58=900"
        second.is_visible.return_value = True
        links.count.return_value = 2
        links.nth.side_effect = [first, second]
        page.locator.return_value = links
        page.content.return_value = '<div class="list-footer">Page 10 of 10 Total: 958</div>'

        with patch("scrape_results_rankings.human_sleep"), patch(
            "scrape_results_rankings.move_mouse_to_locator"
        ) as click:
            clicked = click_results_page_offset(
                page,
                offset=900,
                page_size=100,
                delay_cfg=type("Delay", (), {"min_request_sec": 0, "max_request_sec": 0})(),
                timeout_sec=0.1,
                poll_sec=0,
            )

        self.assertTrue(clicked)
        click.assert_called_once_with(page, second)
        page.goto.assert_not_called()

    def test_pagination_click_propagates_http_429_without_retrying(self):
        page = MagicMock()
        page.url = "https://results.ittf.link/ranking"
        link = MagicMock()
        link.get_attribute.return_value = "/ranking/list/58?limitstart58=900"
        link.is_visible.return_value = True
        links = MagicMock()
        links.count.return_value = 1
        links.nth.return_value = link
        page.locator.return_value = links
        response_handler = None

        def register(_event, handler):
            nonlocal response_handler
            response_handler = handler

        page.on.side_effect = register
        response = MagicMock()
        response.status = 429
        response.status_text = "Too Many Requests"
        response.url = "https://results.ittf.link/ranking/list/58?limitstart58=900"
        response.headers = {"retry-after": "420"}

        def click_once(_page, _locator):
            assert response_handler is not None
            response_handler(response)

        with patch("scrape_results_rankings.human_sleep"), patch(
            "scrape_results_rankings.move_mouse_to_locator", side_effect=click_once
        ) as click:
            with self.assertRaises(RiskControlTriggered) as raised:
                click_results_page_offset(
                    page,
                    offset=900,
                    page_size=100,
                    delay_cfg=type("Delay", (), {"min_request_sec": 0, "max_request_sec": 0})(),
                )

        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(raised.exception.retry_after_sec, 420)
        click.assert_called_once_with(page, link)
        page.goto.assert_not_called()

    def test_fetches_each_scattered_target_page_once_and_merges_missing_rows(self):
        weekly = [self._weekly_row(index) for index in range(350)]
        missing_indexes = {37, 148, 249}
        existing = [
            self._results_row(index)
            for index in range(350)
            if index not in missing_indexes
        ]
        fetched: list[int] = []
        progress: list[tuple[int, list[str]]] = []

        def fetch_page(offset: int) -> list[dict]:
            fetched.append(offset)
            end = min(offset + 100, len(weekly))
            return [self._results_row(index) for index in range(offset, end)]

        recovered, page_checkpoints = recover_missing_results_pages(
            weekly,
            existing,
            page_size=100,
            reported_total=350,
            fetch_page=fetch_page,
            on_progress=lambda rows, checkpoints: progress.append(
                (len(rows), sorted(checkpoints))
            ),
        )

        self.assertEqual(fetched, [0, 100, 200])
        self.assertEqual(len(recovered), 350)
        self.assertEqual(sorted(page_checkpoints), ["0", "100", "200"])
        self.assertEqual(progress, [(348, ["0"]), (349, ["0", "100"]), (350, ["0", "100", "200"])])

    def test_searches_adjacent_page_when_tied_rank_shifted_across_boundary(self):
        weekly = [self._weekly_row(index) for index in range(201)]
        weekly[99]["rank"] = 100
        weekly[100]["rank"] = 100
        existing = [
            self._results_row(index, rank=weekly[index]["rank"])
            for index in range(201)
            if index != 100
        ]
        fetched: list[int] = []

        def fetch_page(offset: int) -> list[dict]:
            fetched.append(offset)
            if offset == 100:
                indexes = [99, *range(101, 200)]
            elif offset == 0:
                indexes = [*range(0, 99), 100]
            else:
                indexes = [200]
            return [
                self._results_row(index, rank=weekly[index]["rank"])
                for index in indexes
            ]

        recovered, _page_checkpoints = recover_missing_results_pages(
            weekly,
            existing,
            page_size=100,
            reported_total=201,
            fetch_page=fetch_page,
        )

        self.assertEqual(fetched, [100, 0])
        self.assertEqual(len(recovered), 201)

    def test_skips_checkpointed_primary_page_and_searches_neighbor(self):
        weekly = [self._weekly_row(index) for index in range(201)]
        weekly[99]["rank"] = 100
        weekly[100]["rank"] = 100
        existing = [
            self._results_row(index, rank=weekly[index]["rank"])
            for index in range(201)
            if index != 100
        ]
        fetched: list[int] = []

        def fetch_page(offset: int) -> list[dict]:
            fetched.append(offset)
            indexes = [*range(0, 99), 100] if offset == 0 else [200]
            return [
                self._results_row(index, rank=weekly[index]["rank"])
                for index in indexes
            ]

        recovered, _page_checkpoints = recover_missing_results_pages(
            weekly,
            existing,
            page_size=100,
            reported_total=201,
            fetch_page=fetch_page,
            completed_offsets={100},
        )

        self.assertEqual(fetched, [0])
        self.assertEqual(len(recovered), 201)


class ResultsCheckpointTests(unittest.TestCase):
    def test_risk_checkpoint_records_retry_after_and_resume_not_before(self):
        now = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)

        meta = add_risk_cooldown_meta(
            {"output_file": "partial.json"},
            RiskControlTriggered("HTTP 429", status=429, retry_after_sec=300),
            now=now,
        )

        self.assertEqual(meta["http_status"], 429)
        self.assertEqual(meta["retry_after_sec"], 300)
        self.assertEqual(
            meta["resume_not_before"],
            (now + timedelta(seconds=300)).isoformat(),
        )

    def test_resume_wait_seconds_reads_failed_checkpoint_cooldown(self):
        now = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)
        checkpoint = MagicMock()
        checkpoint.data = {
            "failed": {
                "ranking-key": {
                    "meta": {
                        "resume_not_before": (now + timedelta(seconds=180)).isoformat(),
                    }
                }
            }
        }

        self.assertEqual(
            results_resume_wait_seconds(checkpoint, "ranking-key", now=now),
            180,
        )

    def test_checkpoint_meta_preserves_page_progress(self):
        meta = build_results_checkpoint_meta(
            Path("partial.json"),
            {
                "rankings": [{"player_id": "111"}],
                "site_total_players": 1,
                "page_size": 100,
                "page_checkpoints": {"400": {"status": "complete", "row_count": 100}},
                "next_page_url": "https://results.ittf.link/ranking?limitstart58=500",
            },
        )

        self.assertEqual(meta["page_size"], 100)
        self.assertEqual(meta["page_checkpoints"]["400"]["status"], "complete")
        self.assertEqual(meta["next_page_url"], "https://results.ittf.link/ranking?limitstart58=500")

    def test_finds_completed_results_output_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            snapshot = tmp / "results_women_top1000_20260616T133056.json"
            snapshot.write_text(json.dumps({"rankings": []}), encoding="utf-8")
            checkpoint = CheckpointStore(tmp / "checkpoint.json")
            checkpoint.mark_done(
                "results-ranking|women|top:1000|results_women_top1000_20260616T133056.json",
                meta={"output_file": str(snapshot), "total_players": 952},
            )

            self.assertEqual(find_completed_results_output(checkpoint, "women", 1000), snapshot)

    def test_rejects_resume_snapshot_shorter_than_weekly_ranking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            weekly = tmp / "women_singles_top1000_week30.json"
            results = tmp / "results_women_top1000.json"
            weekly.write_text(
                json.dumps({"total_players": 958, "rankings": [{"rank": rank} for rank in range(1, 959)]}),
                encoding="utf-8",
            )
            results.write_text(
                json.dumps({"total_players": 825, "rankings": [{"rank": rank} for rank in range(1, 826)]}),
                encoding="utf-8",
            )

            complete, reason = is_results_snapshot_complete(results, weekly, top_n=1000)

        self.assertFalse(complete)
        self.assertIn("825", reason)
        self.assertIn("958", reason)

    def test_rejects_resume_snapshot_shorter_than_current_page_total(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            weekly = tmp / "women_singles_top1000_week30.json"
            results = tmp / "results_women_top1000.json"
            weekly.write_text(
                json.dumps({"total_players": 958, "rankings": [{"rank": rank} for rank in range(1, 959)]}),
                encoding="utf-8",
            )
            results.write_text(
                json.dumps(
                    {
                        "total_players": 958,
                        "site_total_players": 958,
                        "rankings": [{"rank": rank} for rank in range(1, 959)],
                    }
                ),
                encoding="utf-8",
            )

            complete, reason = is_results_snapshot_complete(
                results,
                weekly,
                top_n=1000,
                reported_total=960,
            )

        self.assertFalse(complete)
        self.assertIn("958", reason)
        self.assertIn("960", reason)

    def test_rejects_complete_snapshot_with_player_id_profile_url_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            weekly = tmp / "women_singles_top1_week30.json"
            results = tmp / "results_women_top1.json"
            weekly.write_text(
                json.dumps({"total_players": 1, "rankings": [{"rank": 1}]}),
                encoding="utf-8",
            )
            results.write_text(
                json.dumps(
                    {
                        "category": "women",
                        "total_players": 1,
                        "site_total_players": 1,
                        "rankings": [
                            {
                                "rank": 1,
                                "name": "Player One",
                                "player_id": "111",
                                "profile_url": "https://results.ittf.link/profile?vw_profiles___player_id_raw=222",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            complete, reason = is_results_snapshot_complete(results, weekly, top_n=1)

        self.assertFalse(complete)
        self.assertIn("player ID", reason)

    def test_completed_checkpoint_ignores_incomplete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            weekly = tmp / "women_singles_top1000_week30.json"
            snapshot = tmp / "results_women_top1000.json"
            weekly.write_text(
                json.dumps({"total_players": 958, "rankings": [{"rank": rank} for rank in range(1, 959)]}),
                encoding="utf-8",
            )
            snapshot.write_text(
                json.dumps({"total_players": 825, "rankings": [{"rank": rank} for rank in range(1, 826)]}),
                encoding="utf-8",
            )
            checkpoint = CheckpointStore(tmp / "checkpoint.json")
            checkpoint.mark_done(
                "results-ranking|women|top:1000|results_women_top1000.json",
                meta={"output_file": str(snapshot), "total_players": 825},
            )

            selected = find_completed_results_output(
                checkpoint,
                "women",
                1000,
                weekly_file=weekly,
            )

        self.assertIsNone(selected)

    def test_extracts_reported_total_from_pagination_text(self):
        html = """
        <div class="list-footer">
          <span>Page 1 of 10</span>
          <span>Total: 958</span>
        </div>
        """

        self.assertEqual(extract_results_reported_total(html), 958)

    def test_rejects_scrape_that_stops_before_reported_total(self):
        with self.assertRaisesRegex(RuntimeError, "825.*958"):
            validate_scraped_results_count(
                [{"rank": rank} for rank in range(1, 826)],
                top_n=1000,
                reported_total=958,
            )

    def test_output_distinguishes_site_rows_from_database_recovery(self):
        payload = build_output_payload(
            [{"rank": 1}, {"rank": 2}],
            "women",
            "https://results.ittf.link/ranking",
            pages_scraped=1,
            site_total_players=1,
            db_profile_recovered=1,
            page_size=100,
            page_checkpoints={"0": {"status": "complete", "row_count": 2}},
        )

        self.assertEqual(payload["total_players"], 2)
        self.assertEqual(payload["site_total_players"], 1)
        self.assertEqual(payload["db_profile_recovered"], 1)
        self.assertEqual(payload["page_size"], 100)
        self.assertEqual(payload["page_checkpoints"]["0"]["status"], "complete")

    def test_partial_snapshot_requires_unique_ids_matching_profile_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot = Path(tmpdir) / "results_women_top1000_20260721T112114.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "category": "women",
                        "pages_scraped": 1,
                        "source_reported_total": 958,
                        "rankings": [
                            {
                                "rank": 1,
                                "name": "Player One",
                                "player_id": "111",
                                "profile_url": "https://results.ittf.link/profile?vw_profiles___player_id_raw=222",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            valid, reason = validate_partial_results_snapshot(snapshot, "women", 1000)

        self.assertFalse(valid)
        self.assertIn("player ID", reason)

    def test_partial_snapshot_must_be_a_prefix_starting_at_rank_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot = Path(tmpdir) / "results_women_top1000_20260721T131141.json"
            rows = [
                {
                    "rank": rank,
                    "name": f"Player {rank}",
                    "player_id": str(100000 + rank),
                    "profile_url": f"https://results.ittf.link/profile?vw_profiles___player_id_raw={100000 + rank}",
                }
                for rank in range(801, 959)
            ]
            snapshot.write_text(
                json.dumps(
                    {
                        "category": "women",
                        "pages_scraped": 2,
                        "source_reported_total": 958,
                        "rankings": rows,
                    }
                ),
                encoding="utf-8",
            )

            valid, reason = validate_partial_results_snapshot(snapshot, "women", 1000)

        self.assertFalse(valid)
        self.assertIn("rank 1", reason)

    def test_resumable_snapshot_prefers_greater_verified_coverage_over_recency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            older = output_dir / "results_women_top1000_20260720T100000.json"
            newer = output_dir / "results_women_top1000_20260721T100000.json"

            def write_snapshot(path: Path, count: int) -> None:
                rows = [
                    {
                        "rank": rank,
                        "name": f"Player {rank}",
                        "player_id": str(100000 + rank),
                        "profile_url": f"https://results.ittf.link/profile?vw_profiles___player_id_raw={100000 + rank}",
                    }
                    for rank in range(1, count + 1)
                ]
                path.write_text(
                    json.dumps(
                        {
                            "category": "women",
                            "pages_scraped": max(1, count // 100),
                            "source_reported_total": 958,
                            "rankings": rows,
                        }
                    ),
                    encoding="utf-8",
                )

            write_snapshot(older, 900)
            write_snapshot(newer, 825)

            selected = find_resumable_results_output(output_dir, "women", 1000)

        self.assertEqual(selected, older)

    def test_finds_newest_valid_partial_snapshot_without_failed_checkpoint_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            older = output_dir / "results_women_top1000_20260720T100000.json"
            newer = output_dir / "results_women_top1000_20260721T100000.json"
            row = {
                "rank": 1,
                "name": "Player One",
                "player_id": "111",
                "profile_url": "https://results.ittf.link/profile?vw_profiles___player_id_raw=111",
            }
            for path, pages in ((older, 1), (newer, 2)):
                path.write_text(
                    json.dumps(
                        {
                            "category": "women",
                            "pages_scraped": pages,
                            "source_reported_total": 958,
                            "rankings": [row],
                        }
                    ),
                    encoding="utf-8",
                )

            selected = find_resumable_results_output(output_dir, "women", 1000)

        self.assertEqual(selected, newer)

    def test_builds_resume_url_from_live_pagination_template(self):
        html = """
        <a rel="next" href="/index.php/ranking/list/58?resetfilters=0&amp;limitstart58=25">Next</a>
        """

        url = build_results_resume_url(
            html,
            "https://results.ittf.link/index.php/ranking",
            offset=825,
        )

        self.assertEqual(
            url,
            "https://results.ittf.link/index.php/ranking/list/58?resetfilters=0&limitstart58=825",
        )

    def test_scrape_continues_from_existing_rows_without_refetching_them(self):
        existing = [
            {
                "rank": rank,
                "name": f"Player {rank}",
                "player_id": str(100000 + rank),
                "profile_url": f"https://results.ittf.link/profile?vw_profiles___player_id_raw={100000 + rank}",
            }
            for rank in range(1, 826)
        ]
        html = """
        <div class="list-footer">Page 34 of 39 Total: 958</div>
        <table id="list_58_com_fabrik_58"><tbody><tr>
          <td></td><td>826</td><td></td><td>1</td>
          <td><a href="/profile?vw_profiles___player_id_raw=200826">Player 826</a></td>
          <td><img title="AAA"></td><td>AAA</td><td>EUROPE</td>
        </tr></tbody></table>
        """
        page = MagicMock()
        page.content.return_value = html

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "partial.json"
            rows = scrape_results_rankings(
                page,
                "women",
                826,
                type("Delay", (), {"min_request_sec": 0, "max_request_sec": 0})(),
                output,
                initial_rankings=existing,
                initial_pages_scraped=33,
                initial_reported_total=958,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 826)
        self.assertEqual(rows[824]["rank"], 825)
        self.assertEqual(rows[825]["rank"], 826)
        self.assertEqual(payload["pages_scraped"], 34)

    def test_scrape_stops_at_reported_total_on_last_page(self):
        existing = [
            {
                "rank": rank,
                "name": f"Player {rank}",
                "player_id": str(100000 + rank),
                "profile_url": f"https://results.ittf.link/profile?vw_profiles___player_id_raw={100000 + rank}",
            }
            for rank in range(1, 901)
        ]
        rows = "".join(
            f"""<tr><td></td><td>{rank}</td><td></td><td>1</td>
            <td><a href=\"/profile?vw_profiles___player_id_raw={100000 + rank}\">Player {rank}</a></td>
            <td><img title=\"AAA\"></td><td>AAA</td><td>EUROPE</td></tr>"""
            for rank in range(901, 959)
        )
        page = MagicMock()
        page.url = "https://results.ittf.link/ranking"
        page.content.return_value = (
            '<div class="list-footer">Page 10 of 10 Total: 958</div>'
            f'<table id="list_58_com_fabrik_58"><tbody>{rows}</tbody></table>'
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "scrape_results_rankings.click_next_page_if_any"
        ) as next_page, patch("scrape_results_rankings.human_sleep"):
            output = Path(tmpdir) / "partial.json"
            result = scrape_results_rankings(
                page,
                "women",
                1000,
                type("Delay", (), {"min_request_sec": 0, "max_request_sec": 0})(),
                output,
                initial_rankings=existing,
                initial_reported_total=958,
                page_size=100,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(len(result), 958)
        self.assertIn("900", payload["page_checkpoints"])
        next_page.assert_not_called()


class DatabaseProfileCandidateTests(unittest.TestCase):
    def _create_database(self, db_path: Path, players: list[tuple[int, str, str, str]]) -> None:
        connection = sqlite3.connect(db_path)
        connection.executescript(
            """
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                country_code TEXT NOT NULL
            );
            CREATE TABLE player_profiles (
                player_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                english_name TEXT,
                profile_url TEXT
            );
            """
        )
        for player_id, name, country_code, profile_url in players:
            connection.execute(
                "INSERT INTO players VALUES (?, ?, ?)",
                (player_id, name, country_code),
            )
            connection.execute(
                "INSERT INTO player_profiles VALUES (?, ?, ?, ?)",
                (str(player_id), name, name, profile_url),
            )
        connection.commit()
        connection.close()

    def test_finds_candidates_by_normalized_name_and_country_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_database(
                db_path,
                [
                    (205829, "YEUNG  Yee Lam", "HKG", "https://results.ittf.link/profile/205829"),
                    (999999, "YEUNG Yee Lam", "USA", "https://results.ittf.link/profile/999999"),
                ],
            )

            candidates = find_db_profile_candidates(
                db_path,
                {"name": "yeung yee lam", "country_code": "HKG"},
            )

        self.assertEqual(
            candidates,
            [
                {
                    "player_id": "205829",
                    "name": "YEUNG Yee Lam",
                    "english_name": "YEUNG Yee Lam",
                    "country_code": "HKG",
                    "profile_url": "https://results.ittf.link/profile/205829",
                }
            ],
        )

    def test_recovers_candidate_only_when_profile_rank_matches_weekly_rank(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_database(
                db_path,
                [(205829, "YEUNG Yee Lam", "HKG", "https://results.ittf.link/profile/205829")],
            )
            weekly_rows = [
                {"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}
            ]

            recovered = recover_missing_players_from_db(
                weekly_rows,
                [],
                db_path,
                profile_loader=lambda candidate: {"current_rank": 770},
            )

        self.assertEqual(
            recovered,
            [
                {
                    "rank": 770,
                    "name": "YEUNG Yee Lam",
                    "english_name": "YEUNG Yee Lam",
                    "points": 3,
                    "country": "HKG",
                    "country_code": "HKG",
                    "player_id": "205829",
                    "profile_url": "https://results.ittf.link/profile/205829",
                    "id_resolution_hint": "db_profile_rank",
                }
            ],
        )

    def test_missing_database_leaves_player_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recovered = recover_missing_players_from_db(
                [{"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}],
                [],
                Path(tmpdir) / "missing.db",
                profile_loader=lambda candidate: {"current_rank": 770},
            )

        self.assertEqual(recovered, [])

    def test_browser_recovery_scrapes_database_profile_with_weekly_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "ittf.db"
            weekly_path = tmp / "weekly.json"
            self._create_database(
                db_path,
                [(205829, "YEUNG Yee Lam", "HKG", "https://results.ittf.link/profile/205829")],
            )
            weekly_path.write_text(
                json.dumps(
                    {
                        "rankings": [
                            {"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                weekly_file=str(weekly_path),
                db_path=str(db_path),
                aliases=None,
                profile_dir=str(tmp / "profiles"),
                avatar_dir=str(tmp / "avatars"),
                category="women",
            )
            delay = type(
                "Delay",
                (),
                {
                    "min_request_sec": 0,
                    "max_request_sec": 0,
                    "min_player_gap_sec": 0,
                    "max_player_gap_sec": 0,
                },
            )()
            checkpoint = CheckpointStore(tmp / "checkpoint.json")

            with patch(
                "scrape_results_rankings.scrape_player_profile",
                return_value=({"current_rank": 770}, True),
            ) as scrape_profile:
                recovered = recover_missing_profiles_with_browser(
                    object(),
                    [],
                    args,
                    delay,
                    checkpoint,
                )

        self.assertEqual(recovered[0]["player_id"], "205829")
        scraped_player = scrape_profile.call_args.args[2]
        self.assertEqual(scraped_player["rank"], 770)
        self.assertEqual(scraped_player["points"], 3)
        self.assertFalse(scrape_profile.call_args.kwargs["resume"])

    def test_browser_recovery_honors_resume_for_database_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "ittf.db"
            weekly_path = tmp / "weekly.json"
            self._create_database(
                db_path,
                [(205829, "YEUNG Yee Lam", "HKG", "https://results.ittf.link/profile/205829")],
            )
            weekly_path.write_text(
                json.dumps(
                    {
                        "rankings": [
                            {"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                weekly_file=str(weekly_path),
                db_path=str(db_path),
                aliases=None,
                profile_dir=str(tmp / "profiles"),
                avatar_dir=str(tmp / "avatars"),
                category="women",
                resume=True,
            )
            checkpoint = CheckpointStore(tmp / "checkpoint.json")

            with patch(
                "scrape_results_rankings.scrape_player_profile",
                return_value=({"current_rank": 770}, False),
            ) as scrape_profile:
                recover_missing_profiles_with_browser(
                    object(),
                    [],
                    args,
                    type("Delay", (), {})(),
                    checkpoint,
                )

        self.assertTrue(scrape_profile.call_args.kwargs["resume"])

    def test_profile_loader_failure_leaves_player_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_database(
                db_path,
                [(205829, "YEUNG Yee Lam", "HKG", "https://results.ittf.link/profile/205829")],
            )

            def fail_profile_load(_candidate):
                raise RuntimeError("profile unavailable")

            recovered = recover_missing_players_from_db(
                [{"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}],
                [],
                db_path,
                profile_loader=fail_profile_load,
            )

        self.assertEqual(recovered, [])

    def test_profile_rank_mismatch_leaves_player_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_database(
                db_path,
                [(205829, "YEUNG Yee Lam", "HKG", "https://results.ittf.link/profile/205829")],
            )

            recovered = recover_missing_players_from_db(
                [{"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}],
                [],
                db_path,
                profile_loader=lambda candidate: {"current_rank": 771},
            )

        self.assertEqual(recovered, [])

    def test_profile_rank_disambiguates_same_name_country_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_database(
                db_path,
                [
                    (111, "SAME Name", "AAA", "https://results.ittf.link/profile/111"),
                    (222, "SAME Name", "AAA", "https://results.ittf.link/profile/222"),
                ],
            )

            recovered = recover_missing_players_from_db(
                [{"rank": 50, "name": "SAME Name", "country_code": "AAA", "points": 10}],
                [],
                db_path,
                profile_loader=lambda candidate: {
                    "current_rank": 50 if candidate["player_id"] == "222" else 60
                },
            )

        self.assertEqual([row["player_id"] for row in recovered], ["222"])

    def test_multiple_profile_rank_matches_remain_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_database(
                db_path,
                [
                    (111, "SAME Name", "AAA", "https://results.ittf.link/profile/111"),
                    (222, "SAME Name", "AAA", "https://results.ittf.link/profile/222"),
                ],
            )

            recovered = recover_missing_players_from_db(
                [{"rank": 50, "name": "SAME Name", "country_code": "AAA", "points": 10}],
                [],
                db_path,
                profile_loader=lambda candidate: {"current_rank": 50},
            )

        self.assertEqual(recovered, [])


if __name__ == "__main__":
    unittest.main()
