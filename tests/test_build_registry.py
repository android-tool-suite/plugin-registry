import importlib.util
import pathlib
import unittest
from unittest import mock


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

        entry = MODULE.build_release_entry(source, release, metadata, "release")

        self.assertEqual("sample", entry["id"])
        self.assertEqual("release", entry["channel"])
        self.assertEqual("ab" * 32, entry["sha256"])
        self.assertEqual(12, entry["size"])
        self.assertNotIn("artifactName", entry)

    def test_debug_entry_uses_metadata_artifact_and_commit(self):
        source = {"repository": "owner/sample", "type": "plugin", "tag": "debug"}
        release = {
            "tag_name": "debug",
            "html_url": "https://github.test/debug",
            "published_at": "2026-08-07T00:00:00Z",
            "assets": [
                {
                    "name": "sample.atsplugin",
                    "browser_download_url": "https://github.test/sample.atsplugin",
                    "size": 21,
                    "digest": "sha256:" + "ef" * 32,
                }
            ],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "plugin",
            "channel": "debug",
            "commitSha": "a" * 40,
            "id": "sample",
            "title": "Sample Debug",
            "versionName": "1.1.0",
            "versionCode": 2,
            "artifactName": "sample.atsplugin",
        }

        entry = MODULE.build_release_entry(source, release, metadata, "debug")

        self.assertEqual("debug", entry["channel"])
        self.assertEqual("a" * 40, entry["commitSha"])
        self.assertEqual("ef" * 32, entry["sha256"])

    def test_rejects_missing_digest(self):
        source = {"repository": "owner/app", "artifactName": "app.apk", "type": "app"}
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
            "versionName": "1.0.0",
            "artifactName": "app.apk",
        }
        with self.assertRaises(ValueError):
            MODULE.build_release_entry(source, release, metadata, "release")

    def test_rejects_release_tag_mismatch(self):
        source = {"repository": "owner/app", "artifactName": "app.apk", "type": "app"}
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
            MODULE.build_release_entry(source, release, metadata, "release")

    def test_rejects_channel_mismatch(self):
        source = {"repository": "owner/sample", "type": "plugin", "tag": "debug"}
        release = {
            "tag_name": "debug",
            "html_url": "https://github.test/debug",
            "assets": [],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "plugin",
            "channel": "release",
        }
        with self.assertRaisesRegex(ValueError, "channel mismatch"):
            MODULE.build_release_entry(source, release, metadata, "debug")

    def test_discovers_only_active_official_plugin_repositories(self):
        repositories = [
            {"name": "plugin-one", "full_name": "org/plugin-one"},
            {"name": "plugin-registry", "full_name": "org/plugin-registry"},
            {"name": "plugin-archived", "full_name": "org/plugin-archived", "archived": True},
            {"name": "workspace", "full_name": "org/workspace"},
        ]
        configuration = {
            "organization": "org",
            "repositoryNamePrefix": "plugin-",
            "excludedRepositories": ["org/plugin-registry"],
        }

        with mock.patch.object(MODULE, "request_json", return_value=repositories):
            sources = MODULE.discover_plugin_sources(configuration)

        self.assertEqual([{"repository": "org/plugin-one", "type": "plugin"}], sources)


if __name__ == "__main__":
    unittest.main()
