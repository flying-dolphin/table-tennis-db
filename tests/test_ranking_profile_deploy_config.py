from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RankingProfileDeployConfigTests(unittest.TestCase):
    def test_runtime_bundle_includes_ranking_profile_import_dependencies(self):
        upload_script = (ROOT / "deploy" / "server" / "upload_runtime.ps1").read_text(encoding="utf-8")

        required_paths = [
            "scripts\\db\\import_players.py",
            "scripts\\db\\import_rankings.py",
            "scripts\\db\\config.py",
            "scripts\\lib\\career_best.py",
            "data\\player_country_history.json",
        ]

        for required_path in required_paths:
            self.assertIn(required_path, upload_script)

    def test_data_update_script_imports_players_before_rankings(self):
        update_script = (ROOT / "deploy" / "server" / "update_rankings_profiles.sh").read_text(encoding="utf-8")

        players_pos = update_script.index("scripts/db/import_players.py")
        rankings_pos = update_script.index("scripts/db/import_rankings.py")

        self.assertLess(players_pos, rankings_pos)
        self.assertIn("--file", update_script)

    def test_data_update_script_backs_up_database_before_imports(self):
        update_script = (ROOT / "deploy" / "server" / "update_rankings_profiles.sh").read_text(encoding="utf-8")

        backup_pos = update_script.index("\n    backup_remote_database\n")
        imports_pos = update_script.index("==> Running remote imports")

        self.assertLess(backup_pos, imports_pos)
        self.assertIn("ittf-before-ranking-profile-", update_script)


if __name__ == "__main__":
    unittest.main()
