"""Exercise shell entry points with a fake crontab, never the user's crontab."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.ac2026.common import ROOT

RESOLVER = ROOT / "scripts/ac2026/resolve_python.sh"


class PythonResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.python = self.bin / "python"
        self.python.symlink_to(sys.executable)
        self.env = {**os.environ, "PATH": str(self.bin), "PYTHON_BIN": ""}

    def tearDown(self):
        self.temp.cleanup()

    def resolve(self, **env):
        return subprocess.run(["/bin/bash", "-c", 'source "$1"; ac2026_resolve_python "$2"', "resolver", str(RESOLVER), str(self.root)],
                              env={**self.env, **env}, capture_output=True, text=True)

    def test_missing_venv_falls_back_to_active_python(self):
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.python))

    def test_explicit_python_takes_precedence_over_venv(self):
        venv = self.root / ".venv/bin"
        venv.mkdir(parents=True)
        (venv / "python").symlink_to(sys.executable)
        result = self.resolve(PYTHON_BIN=str(self.python))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.python))

    def test_valid_project_venv_is_preferred_to_path(self):
        venv = self.root / ".venv/bin"
        venv.mkdir(parents=True)
        candidate = venv / "python"
        candidate.symlink_to(sys.executable)
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(candidate))

    def test_invalid_explicit_python_is_not_silently_replaced(self):
        result = self.resolve(PYTHON_BIN=str(self.root / "missing/python"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_BIN", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_unsupported_python_fails_before_running_operations(self):
        unsupported = self.bin / "old-python"
        unsupported.write_text("#!/bin/sh\nexit 1\n")
        unsupported.chmod(0o755)
        result = self.resolve(PYTHON_BIN=str(unsupported))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("3.11", result.stderr)


class CronInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "deployment"
        package = self.root / "scripts/ac2026"
        package.mkdir(parents=True)
        for name in ("__init__.py", "common.py", "generate_crontab.py", "resolve_python.sh", "install_crontab.sh"):
            shutil.copyfile(ROOT / "scripts/ac2026" / name, package / name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "python").symlink_to(sys.executable)
        self.cron_file = self.root / "crontab.txt"
        self.cron_file.write_text("# unrelated task\n0 1 * * * echo keep-me\n")
        crontab = self.bin / "crontab"
        crontab.write_text('''#!/bin/bash
if [[ "$1" == -l ]]; then
    cat "$AC2026_TEST_CRONTAB"
else
    cp "$1" "$AC2026_TEST_CRONTAB"
fi
''')
        crontab.chmod(0o755)
        self.env = {**os.environ, "PYTHON_BIN": "", "PATH": str(self.bin) + os.pathsep + os.environ["PATH"], "AC2026_TEST_CRONTAB": str(self.cron_file)}

    def tearDown(self):
        self.temp.cleanup()

    def install(self, **env):
        return subprocess.run(["/bin/bash", str(self.root / "scripts/ac2026/install_crontab.sh")],
                              env={**self.env, **env}, capture_output=True, text=True)

    def test_install_and_reinstall_preserve_other_jobs_and_need_no_manual_edits(self):
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            content = self.cron_file.read_text()
            self.assertEqual(content.count("# BEGIN ITTF AC2026 3474"), 1)
            self.assertIn("0 1 * * * echo keep-me", content)
            self.assertIn("55 4 26 10 *", content)
            self.assertIn("scripts.ac2026.finalize --skip-refresh", content)
            self.assertNotIn(".venv/bin/python", content)

    def test_invalid_interpreter_leaves_existing_crontab_unchanged(self):
        before = self.cron_file.read_bytes()
        result = self.install(PYTHON_BIN="/not-installed/python")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_BIN", result.stderr)
        self.assertEqual(self.cron_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
