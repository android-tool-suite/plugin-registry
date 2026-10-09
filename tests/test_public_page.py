"""Checks the dependency-free page behavior alongside the offline registry tests."""
import pathlib
import subprocess
import unittest


class PublicPageTest(unittest.TestCase):
    def test_navigation_versions_and_failure_recovery(self):
        script = pathlib.Path(__file__).with_name("public-page.test.js")
        result = subprocess.run(
            ["node", "--test", str(script)],
            text=True, encoding="utf-8", capture_output=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()