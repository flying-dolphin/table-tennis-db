import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scrape_results_rankings as rankings


def ranking_page(first_rank: int, last_rank: int, page_number: int) -> str:
    rows = "".join(
        '<tr><td></td><td>{rank}</td><td></td><td>0</td>'
        '<td><a href="/index.php?player_id_raw={rank}">Player {rank}</a></td>'
        '<td><img title="X"></td><td>X</td><td>Asia</td></tr>'.format(rank=rank)
        for rank in range(first_rank, last_rank + 1)
    )
    return (
        f'<table id="list_58_com_fabrik_58"><tbody>{rows}</tbody></table>'
        f'<div class="list-footer">Page {page_number} of 2 Total: 186</div>'
        '<div class="pagination"><a rel="next" '
        'href="/index.php/ittf-rankings/ittf-ranking-women-singles/list/58?limitstart58=100">Next</a></div>'
    )


class ResultsRankingStartPageTests(unittest.TestCase):
    def test_click_results_page_offset_clicks_target_link(self) -> None:
        class Link:
            clicked = False

            def count(self):
                return 1

            def nth(self, _index):
                return self

            def get_attribute(self, name):
                if name == "href":
                    return "/index.php/ittf-rankings/ittf-ranking-women-singles/list/58?limitstart58=100"
                return None

            def is_visible(self):
                return True

            def scroll_into_view_if_needed(self):
                pass

            def click(self):
                self.clicked = True

        class Page:
            url = rankings.RANKING_URLS["women"]

            def locator(self, _selector):
                return link

            def on(self, *_args):
                pass

            def remove_listener(self, *_args):
                pass

            def wait_for_load_state(self, *_args, **_kwargs):
                pass

            def content(self):
                return ranking_page(101, 186, 2) if link.clicked else ranking_page(1, 100, 1)

        link = Link()
        with (
            patch.object(rankings, "human_sleep"),
            patch.object(rankings, "move_mouse_to_locator"),
            patch.object(rankings, "detect_risk", return_value=None),
        ):
            reached = rankings.click_results_page_offset(
                Page(),
                offset=100,
                page_size=100,
                delay_cfg=rankings.DelayConfig(0, 0, 0, 0),
                timeout_sec=0,
                poll_sec=0,
            )
        self.assertTrue(reached)
        self.assertTrue(link.clicked)

    def test_reset_url_can_use_previous_link_on_last_page(self) -> None:
        html = (
            '<div class="pagination"><a href="/index.php/ittf-rankings/'
            'ittf-ranking-women-singles/list/58?limitstart58=800">Previous</a></div>'
        )
        url = rankings.build_results_resume_url(html, rankings.RANKING_URLS["women"], 0)
        self.assertIsNotNone(url)
        self.assertIn("limitstart58=0", url)

    def test_fresh_reset_uses_url_when_first_page_link_is_not_visible(self) -> None:
        last_html = (
            ranking_page(101, 186, 2)
            .replace('rel="next"', 'title="Previous"')
            .replace("limitstart58=100", "limitstart58=0")
        )

        class Page:
            url = rankings.RANKING_URLS["women"]
            html = last_html

            def content(self):
                return self.html

        page = Page()

        def navigate(_page, url, *_args, **_kwargs):
            self.assertIn("limitstart58=0", url)
            page.html = ranking_page(1, 100, 1)

        with (
            patch.object(rankings, "click_results_page_offset", return_value=False),
            patch.object(rankings, "guarded_goto", side_effect=navigate) as goto,
            patch.object(rankings, "wait_for_results_page_html", side_effect=lambda page, **_: page.content()),
        ):
            rankings.reset_fresh_results_to_first_page(
                page,
                delay_cfg=rankings.DelayConfig(0, 0, 0, 0),
                page_size=100,
            )
        self.assertEqual(goto.call_count, 1)

    def test_fresh_scrape_resets_last_page_before_saving(self) -> None:
        first_html = ranking_page(1, 100, 1)
        last_html = ranking_page(101, 186, 2)

        class Page:
            url = rankings.RANKING_URLS["women"]
            html = last_html

            def content(self) -> str:
                return self.html

        page = Page()
        saved = []

        def click_offset(_page, *, offset, **_kwargs):
            if offset == 0:
                page.html = first_html
            elif offset == 100:
                page.html = last_html
            else:
                self.fail(f"unexpected results page offset {offset}")
            return True

        with (
            patch.object(rankings, "detect_risk", return_value=None),
            patch.object(rankings, "human_sleep"),
            patch.object(rankings, "click_results_page_offset", side_effect=click_offset) as reset,
            patch.object(rankings, "wait_for_results_page_html", side_effect=lambda page, **_: page.content()),
            patch.object(rankings, "save_json", side_effect=lambda _path, payload: saved.append(copy.deepcopy(payload))),
        ):
            result = rankings.scrape_results_rankings(
                page,
                "women",
                1000,
                rankings.DelayConfig(0, 0, 0, 0),
                Path("unused-results.json"),
                page_size=100,
            )

        self.assertEqual([call.kwargs["offset"] for call in reset.call_args_list], [0, 100])
        self.assertEqual(len(result), 186)
        self.assertEqual((result[0]["rank"], result[-1]["rank"]), (1, 186))
        self.assertEqual([len(payload["rankings"]) for payload in saved], [100, 186])
        self.assertIn("limitstart58=100", saved[0]["next_page_url"])


if __name__ == "__main__":
    unittest.main()
