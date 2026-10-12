import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from db.update_inactive_player_ages import (  # noqa: E402
    compute_age,
    latest_ranked_player_ids,
    update_inactive_player_ages,
)


class ComputeAgeTests(unittest.TestCase):
    def test_computes_age_from_birth_year(self):
        self.assertEqual(compute_age(2000, year=2026), 26)

    def test_returns_none_for_missing_birth_year(self):
        self.assertIsNone(compute_age(None, year=2026))

    def test_returns_none_for_future_birth_year(self):
        self.assertIsNone(compute_age(2030, year=2026))


class LatestRankedPlayerIdsTests(unittest.TestCase):
    def _create_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE ranking_snapshots (
                snapshot_id INTEGER PRIMARY KEY,
                category TEXT,
                ranking_week TEXT,
                ranking_date TEXT,
                total_players INTEGER,
                scraped_at TEXT
            );
            CREATE TABLE ranking_entries (
                entry_id INTEGER PRIMARY KEY,
                snapshot_id INTEGER,
                player_id INTEGER,
                rank INTEGER,
                points INTEGER,
                rank_change INTEGER
            );
            """
        )
        conn.execute(
            "INSERT INTO ranking_snapshots VALUES (1, 'women', '2026W1', '2026-01-01', 3, '')"
        )
        conn.execute(
            "INSERT INTO ranking_snapshots VALUES (2, 'women', '2026W2', '2026-01-08', 2, '')"
        )
        conn.executemany(
            "INSERT INTO ranking_entries (snapshot_id, player_id, rank, points) VALUES (?, ?, ?, ?)",
            [(1, 111, 1, 9000), (1, 222, 2, 8000), (2, 111, 1, 9100), (2, 333, 2, 8100)],
        )
        conn.commit()
        conn.close()

    def test_reads_only_latest_snapshot_player_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ittf.db"
            self._create_db(db_path)
            conn = sqlite3.connect(db_path)

            ranked = latest_ranked_player_ids(conn)

            conn.close()

        self.assertEqual(ranked, {111, 333})


class UpdateInactivePlayerAgesTests(unittest.TestCase):
    def _create_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE ranking_snapshots (
                snapshot_id INTEGER PRIMARY KEY,
                category TEXT,
                ranking_week TEXT,
                ranking_date TEXT,
                total_players INTEGER,
                scraped_at TEXT
            );
            CREATE TABLE ranking_entries (
                entry_id INTEGER PRIMARY KEY,
                snapshot_id INTEGER,
                player_id INTEGER,
                rank INTEGER,
                points INTEGER,
                rank_change INTEGER
            );
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                name_zh TEXT,
                slug TEXT UNIQUE NOT NULL,
                country TEXT,
                country_code TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT 'Female',
                birth_year INTEGER,
                age INTEGER,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            "INSERT INTO ranking_snapshots VALUES (1, 'women', '2026W1', '2026-01-01', 1, '')"
        )
        conn.execute(
            "INSERT INTO ranking_entries (snapshot_id, player_id, rank, points) VALUES (1, 111, 1, 9000)"
        )
        # 111 在世排中（不应被更新年龄）；222/333 不在世排中（应被更新）；444 无 birth_year（跳过）
        conn.executemany(
            "INSERT INTO players (player_id, name, slug, country_code, birth_year, age) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (111, "Ranked", "111", "CHN", 1998, 28),
                (222, "Inactive", "222", "JPN", 1990, 35),
                (333, "Retired", "333", "KOR", 2000, 25),
                (444, "NoBirth", "444", "GER", None, None),
            ],
        )
        conn.commit()
        conn.close()

    def test_updates_only_inactive_players_with_birth_year(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "ittf.db"
            state_file = tmp / "state.json"
            self._create_db(db_path)

            result = update_inactive_player_ages(
                str(db_path), year=2026, force=True, dry_run=False, state_file=state_file
            )

            conn = sqlite3.connect(db_path)
            ages = dict(conn.execute("SELECT player_id, age FROM players"))
            conn.close()

            saved = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(result["updated"], 2)
        self.assertEqual(ages[222], 36)
        self.assertEqual(ages[333], 26)
        self.assertEqual(ages[111], 28)  # 世排中，不变
        self.assertIsNone(ages[444])
        self.assertEqual(saved["last_age_update_year"], 2026)

    def test_skips_when_already_updated_this_year(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "ittf.db"
            state_file = tmp / "state.json"
            self._create_db(db_path)
            state_file.write_text(
                json.dumps({"last_age_update_year": 2026}), encoding="utf-8"
            )

            result = update_inactive_player_ages(
                str(db_path), year=2026, force=False, dry_run=False, state_file=state_file
            )

        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped_reason"], "already updated in 2026")

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "ittf.db"
            state_file = tmp / "state.json"
            self._create_db(db_path)

            result = update_inactive_player_ages(
                str(db_path), year=2026, force=True, dry_run=True, state_file=state_file
            )

            conn = sqlite3.connect(db_path)
            ages = dict(conn.execute("SELECT player_id, age FROM players"))
            conn.close()

        self.assertEqual(result["updated"], 2)
        self.assertEqual(ages[222], 35)  # 未写入
        self.assertFalse(state_file.exists())


if __name__ == "__main__":
    unittest.main()
