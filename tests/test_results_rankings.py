import sys
import json
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.checkpoint import CheckpointStore
from scrape_results_rankings import find_completed_results_output, parse_results_ranking_html


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


class ResultsCheckpointTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
