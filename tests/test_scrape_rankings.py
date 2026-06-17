import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from scrape_rankings import build_parser, extract_ranking_meta


class FakePage:
    def __init__(self, html: str):
        self._html = html

    def content(self) -> str:
        return self._html


class ExtractRankingMetaTests(unittest.TestCase):
    def test_parses_visible_ittf_week_and_ordinal_date(self):
        page = FakePage("<div>2026 Week #24 - June 8th</div>")

        ranking_week, ranking_date = extract_ranking_meta(page)

        self.assertEqual(ranking_week, "Week 24, 2026")
        self.assertEqual(ranking_date, "2026-06-08")

    def test_raises_when_ranking_metadata_is_missing(self):
        page = FakePage("<div>Women's Singles Rankings</div>")

        with self.assertRaisesRegex(ValueError, "ranking metadata"):
            extract_ranking_meta(page)


class BuildParserTests(unittest.TestCase):
    def test_accepts_cdp_only_flag(self):
        args = build_parser().parse_args(["--cdp-only"])

        self.assertTrue(args.cdp_only)


if __name__ == "__main__":
    unittest.main()
