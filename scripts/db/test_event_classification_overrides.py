import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DB_DIR = PROJECT_ROOT / "scripts" / "db"


def load_module(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DB_DIR / file_name)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


IMPORT_EVENTS = load_module("import_events_under_test", "import_events.py")
IMPORT_EVENTS_CALENDAR = load_module("import_events_calendar_under_test", "import_events_calendar.py")


class EventClassificationOverrideTests(unittest.TestCase):
    def test_calendar_classifies_asian_games_as_continental_games(self):
        event_type, event_kind = IMPORT_EVENTS_CALENDAR.classify_event_by_name("Asian Games Aichi-Nagoya 2026")

        self.assertEqual(("Continental Games", "--"), (event_type, event_kind))

    def test_calendar_does_not_reclassify_asian_para_games(self):
        event_type, event_kind = IMPORT_EVENTS_CALENDAR.classify_event_by_name("Asian Para Games Aichi-Nagoya 2026")

        self.assertEqual(("Multi sport events", "--"), (event_type, event_kind))

    def test_event_import_overrides_asian_games_source_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            db_path = temp_dir / "ittf.db"
            events_dir = temp_dir / "events"
            events_dir.mkdir()
            self._init_events_schema(db_path)
            self._seed_event_mappings(db_path)

            payload = {
                "scraped_at": "2026-05-12T00:00:00Z",
                "events": [
                    {
                        "event_id": 9001,
                        "year": 2026,
                        "name": "Asian Games Aichi-Nagoya 2026",
                        "name_zh": "2026年爱知·名古屋亚洲运动会",
                        "event_type": "Multi sport events",
                        "event_kind": "--",
                        "event_kind_zh": "",
                        "matches": "0",
                        "start_date": "2026-09-20",
                        "end_date": "2026-09-28",
                        "location": "JPN",
                        "href": "/fake/asian-games",
                    }
                ],
            }
            (events_dir / "events.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                IMPORT_EVENTS.import_events(str(db_path), str(events_dir))

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT event_type_name, category_code FROM events WHERE event_id = ?",
                    (9001,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(("Continental Games", "CONTINENTAL_GAMES"), row)

    def test_event_import_preserves_runtime_fields_on_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            db_path = temp_dir / "ittf.db"
            events_dir = temp_dir / "events"
            events_dir.mkdir()
            self._init_events_schema(db_path)
            self._seed_event_mappings(db_path)

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO events (
                        event_id, year, name, event_type_name, event_kind,
                        lifecycle_status, time_zone, last_synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        9002,
                        2026,
                        "Old Event Name",
                        "Multi sport events",
                        "--",
                        "completed",
                        "Asia/Shanghai",
                        "2026-06-15T00:00:00Z",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            payload = {
                "scraped_at": "2026-06-16T00:00:00Z",
                "events": [
                    {
                        "event_id": 9002,
                        "year": 2026,
                        "name": "Updated Event Name",
                        "event_type": "Multi sport events",
                        "event_kind": "--",
                        "matches": "42",
                    }
                ],
            }
            (events_dir / "events.json").write_text(json.dumps(payload), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                IMPORT_EVENTS.import_events(str(db_path), str(events_dir))

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT name, total_matches, scraped_at,
                           lifecycle_status, time_zone, last_synced_at
                    FROM events
                    WHERE event_id = ?
                    """,
                    (9002,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(
                (
                    "Updated Event Name",
                    42,
                    "2026-06-16T00:00:00Z",
                    "completed",
                    "Asia/Shanghai",
                    "2026-06-15T00:00:00Z",
                ),
                row,
            )

    def _init_events_schema(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE event_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id TEXT NOT NULL UNIQUE,
                    category_name TEXT NOT NULL,
                    category_name_zh TEXT
                );

                CREATE TABLE event_type_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    event_kind TEXT,
                    category_id INTEGER NOT NULL,
                    priority INTEGER DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE events (
                    event_id INTEGER PRIMARY KEY,
                    year INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    name_zh TEXT,
                    event_type_name TEXT,
                    event_kind TEXT,
                    event_kind_zh TEXT,
                    event_category_id INTEGER,
                    category_code TEXT,
                    category_name_zh TEXT,
                    total_matches INTEGER DEFAULT 0,
                    start_date TEXT,
                    end_date TEXT,
                    location TEXT,
                    time_zone TEXT,
                    href TEXT,
                    lifecycle_status TEXT NOT NULL DEFAULT 'upcoming',
                    last_synced_at TEXT,
                    scraped_at TEXT
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_event_mappings(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO event_categories (id, category_id, category_name, category_name_zh) VALUES (1, ?, ?, ?)",
                ("MULTI_SPORT_GAMES", "Multi-Sport Games", "综合运动会"),
            )
            conn.execute(
                "INSERT INTO event_categories (id, category_id, category_name, category_name_zh) VALUES (2, ?, ?, ?)",
                ("CONTINENTAL_GAMES", "Continental Games", "洲际运动会"),
            )
            conn.execute(
                "INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority, is_active) VALUES (?, ?, ?, 10, 1)",
                ("Multi sport events", "--", 1),
            )
            conn.execute(
                "INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority, is_active) VALUES (?, ?, ?, 10, 1)",
                ("Continental Games", "--", 2),
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
