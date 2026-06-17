from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AvatarAssetDeployConfigTests(unittest.TestCase):
    def test_web_compose_mounts_only_runtime_avatar_thumbnail_directories(self):
        compose = (ROOT / "deploy" / "web" / "docker-compose.yml").read_text(encoding="utf-8")

        required_mounts = [
            "web_assets/avatar-thumbs:/app/web/public/images/avatar-thumbs:ro",
            "web_assets/avatar-full-thumbs:/app/web/public/images/avatar-full-thumbs:ro",
        ]

        for required_mount in required_mounts:
            self.assertIn(required_mount, compose)

        forbidden_mounts = [
            "web_assets/avatars:/app/web/public/images/avatars:ro",
            "web_assets/crops:/app/web/public/images/crops:ro",
        ]

        for forbidden_mount in forbidden_mounts:
            self.assertNotIn(forbidden_mount, compose)

    def test_dockerignore_excludes_generated_avatar_assets(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        required_paths = [
            "web/public/images/avatars",
            "web/public/images/crops",
            "web/public/images/avatar-thumbs",
            "web/public/images/avatar-full-thumbs",
        ]

        for required_path in required_paths:
            self.assertIn(required_path, dockerignore)


if __name__ == "__main__":
    unittest.main()
