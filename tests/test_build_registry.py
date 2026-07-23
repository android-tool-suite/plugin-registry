import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "build-registry.py"
SPEC = importlib.util.spec_from_file_location("build_registry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RegistryBuilderTest(unittest.TestCase):
    def test_build_release_entry_uses_github_digest(self):
        source = {
            "id": "sample",
            "repository": "owner/sample",
            "artifactName": "sample.atsplugin",
        }
        release = {
            "tag_name": "v1.0.0",
            "html_url": "https://github.test/release",
            "published_at": "2026-07-24T00:00:00Z",
            "assets": [
                {
                    "name": "sample.atsplugin",
                    "browser_download_url": "https://github.test/sample.atsplugin",
                    "size": 12,
                    "digest": "sha256:" + "ab" * 32,
                }
            ],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "plugin",
            "id": "sample",
            "title": "Sample",
            "versionName": "1.0.0",
            "versionCode": 1,
            "artifactName": "sample.atsplugin",
        }

        entry = MODULE.build_release_entry(source, release, metadata)

        self.assertEqual("sample", entry["id"])
        self.assertEqual("ab" * 32, entry["sha256"])
        self.assertEqual(12, entry["size"])
        self.assertNotIn("artifactName", entry)

    def test_rejects_missing_digest(self):
        source = {
            "repository": "owner/app",
            "artifactName": "app.apk",
        }
        release = {
            "tag_name": "v1.0.0",
            "html_url": "https://github.test/release",
            "assets": [
                {
                    "name": "app.apk",
                    "browser_download_url": "https://github.test/app.apk",
                    "size": 12,
                    "digest": None,
                }
            ],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "app",
            "artifactName": "app.apk",
        }
        with self.assertRaises(ValueError):
            MODULE.build_release_entry(source, release, metadata)

    def test_rejects_release_tag_mismatch(self):
        source = {
            "repository": "owner/app",
            "artifactName": "app.apk",
        }
        release = {
            "tag_name": "v1.0.1",
            "html_url": "https://github.test/release",
            "assets": [
                {
                    "name": "app.apk",
                    "browser_download_url": "https://github.test/app.apk",
                    "size": 12,
                    "digest": "sha256:" + "cd" * 32,
                }
            ],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "app",
            "versionName": "1.0.0",
            "artifactName": "app.apk",
        }
        with self.assertRaises(ValueError):
            MODULE.build_release_entry(source, release, metadata)


if __name__ == "__main__":
    unittest.main()
