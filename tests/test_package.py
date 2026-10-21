"""Installed-package entry points must work outside the source checkout."""

import os
import subprocess
import sys
import tempfile
import unittest


class PackageEntryTests(unittest.TestCase):
    def run_python(self, *arguments):
        environment = os.environ.copy()
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        environment["PYTHONUTF8"] = "1"
        with tempfile.TemporaryDirectory(prefix="easytextdiff-package-") as directory:
            result = subprocess.run(
                [sys.executable, *arguments], cwd=directory, env=environment,
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_import_does_not_load_qt_or_start_an_application(self):
        result = self.run_python(
            "-c",
            "import sys; import easytextdiff; "
            "assert not any(name == 'PyQt5' or name.startswith('PyQt5.') "
            "for name in sys.modules); print(easytextdiff.__name__)",
        )
        self.assertEqual(result.stdout.strip(), "easytextdiff")

    def test_module_help_works_from_an_unrelated_directory(self):
        result = self.run_python("-m", "easytextdiff", "--help")
        self.assertIn("EasyTextDiff", result.stdout)
        self.assertIn("--demo", result.stdout)
        self.assertIn("--help", result.stdout)


if __name__ == "__main__":
    unittest.main()
