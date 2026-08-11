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
        self.assertEqual("v1.0.0", entry["tagName"])
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

    def test_debug_snapshot_tag_must_match_metadata_commit(self):
        source = {"repository": "owner/sample", "type": "plugin", "tag": "debug"}
        release = {
            "tag_name": "debug-" + "a" * 40,
            "html_url": "https://github.test/debug-snapshot",
            "assets": [{
                "name": "sample.atsplugin",
                "browser_download_url": "https://github.test/sample.atsplugin",
                "size": 21,
                "digest": "sha256:" + "ef" * 32,
            }],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "plugin",
            "channel": "debug",
            "commitSha": "b" * 40,
            "id": "sample",
            "artifactName": "sample.atsplugin",
        }

        with self.assertRaisesRegex(ValueError, "snapshot tag mismatch"):
            MODULE.build_release_entry(source, release, metadata, "debug")

    def test_release_history_filters_drafts_and_other_tags(self):
        releases = [
            {"tag_name": "v2.0.0", "draft": False, "prerelease": False},
            {"tag_name": "v1.0.0", "draft": True, "prerelease": False},
            {"tag_name": "debug", "draft": False, "prerelease": True},
            {"tag_name": "plugin-sdk-v1.0.0", "draft": False, "prerelease": False},
        ]
        with mock.patch.object(MODULE, "request_json", return_value=releases):
            result = MODULE.releases_for_channel("owner/app", "release", "debug")

        self.assertEqual(["v2.0.0"], [release["tag_name"] for release in result])

    def test_debug_history_includes_rolling_and_commit_snapshots(self):
        releases = [
            {"tag_name": "debug", "draft": False, "prerelease": True},
            {"tag_name": "debug-" + "a" * 40, "draft": False, "prerelease": True},
            {"tag_name": "debug-short", "draft": False, "prerelease": True},
            {"tag_name": "v1.0.0", "draft": False, "prerelease": False},
        ]
        with mock.patch.object(MODULE, "request_json", return_value=releases):
            result = MODULE.releases_for_channel("owner/app", "debug", "debug")

        self.assertEqual(
            ["debug", "debug-" + "a" * 40],
            [release["tag_name"] for release in result],
        )

    def test_fetch_entries_prefers_snapshot_over_rolling_duplicate(self):
        commit_sha = "a" * 40
        releases = [
            {"tag_name": "debug", "published_at": "2026-08-01T00:00:00Z"},
            {
                "tag_name": "debug-" + commit_sha,
                "published_at": "2026-08-02T00:00:00Z",
            },
        ]

        def build_entry(_source, release, _metadata, _channel):
            return {
                "commitSha": commit_sha,
                "tagName": release["tag_name"],
                "publishedAt": release["published_at"],
                "versionCode": 1,
            }

        with mock.patch.object(MODULE, "releases_for_channel", return_value=releases), \
                mock.patch.object(MODULE, "asset_by_name", return_value={"browser_download_url": "metadata"}), \
                mock.patch.object(MODULE, "request_json", return_value={}), \
                mock.patch.object(MODULE, "build_release_entry", side_effect=build_entry):
            entries = MODULE.fetch_entries(
                {"repository": "owner/app"}, "debug", "debug"
            )

        self.assertEqual(1, len(entries))
        self.assertEqual("debug-" + commit_sha, entries[0]["tagName"])

    def test_fetch_entries_skips_temporarily_incomplete_rolling_debug(self):
        commit_sha = "a" * 40
        rolling = {"tag_name": "debug", "assets": []}
        snapshot = {"tag_name": "debug-" + commit_sha}
        snapshot_entry = {
            "commitSha": commit_sha,
            "tagName": snapshot["tag_name"],
            "publishedAt": "2026-08-02T00:00:00Z",
            "versionCode": 1,
        }

        with mock.patch.object(
            MODULE, "releases_for_channel", return_value=[rolling, snapshot]
        ), mock.patch.object(
            MODULE,
            "load_release_entry",
            side_effect=[
                MODULE.MissingReleaseAssetError("assets are being replaced"),
                snapshot_entry,
            ],
        ):
            entries = MODULE.fetch_entries(
                {"repository": "owner/app"}, "debug", "debug"
            )

        self.assertEqual([snapshot_entry], entries)

    def test_fetch_entry_falls_back_to_snapshot_during_rolling_update(self):
        rolling = {"tag_name": "debug", "assets": []}
        snapshot_entry = {"tagName": "debug-" + "a" * 40}

        with mock.patch.object(
            MODULE, "release_for_channel", return_value=rolling
        ), mock.patch.object(
            MODULE,
            "load_release_entry",
            side_effect=MODULE.MissingReleaseAssetError("metadata is not uploaded"),
        ), mock.patch.object(
            MODULE, "fetch_entries", return_value=[snapshot_entry]
        ):
            entry = MODULE.fetch_entry(
                {"repository": "owner/app"}, "debug", "debug"
            )

        self.assertEqual(snapshot_entry, entry)

    def test_fetch_entry_keeps_formal_release_asset_validation_strict(self):
        release = {"tag_name": "v1.0.0", "assets": []}

        with mock.patch.object(
            MODULE, "release_for_channel", return_value=release
        ):
            with self.assertRaises(MODULE.MissingReleaseAssetError):
                MODULE.fetch_entry(
                    {"repository": "owner/app"}, "release", "debug"
                )

    def test_debug_app_uses_channel_artifact_and_package(self):
        source = {
            "repository": "owner/app",
            "type": "app",
            "tag": "debug",
            "artifactNames": {
                "release": "app.apk",
                "debug": "app-debug.apk",
            },
        }
        release = {
            "tag_name": "debug",
            "html_url": "https://github.test/debug",
            "published_at": "2026-08-07T00:00:00Z",
            "assets": [{
                "name": "app-debug.apk",
                "browser_download_url": "https://github.test/app-debug.apk",
                "size": 42,
                "digest": "sha256:" + "ac" * 32,
            }],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "app",
            "channel": "debug",
            "commitSha": "b" * 40,
            "packageName": "com.androidtoolsuite.app.debug",
            "versionName": "1.3.1",
            "versionCode": 13,
            "minSdk": 24,
            "artifactName": "app-debug.apk",
        }

        entry = MODULE.build_release_entry(source, release, metadata, "debug")

        self.assertEqual("com.androidtoolsuite.app.debug", entry["packageName"])
        self.assertEqual("debug", entry["channel"])
        self.assertEqual("b" * 40, entry["commitSha"])

    def test_build_debug_index_includes_app(self):
        sources = {
            "schemaVersion": 2,
            "app": {"repository": "owner/app"},
            "pluginDiscovery": {},
            "debugTag": "debug",
        }
        app_entry = {"packageName": "com.androidtoolsuite.app.debug"}
        with mock.patch.object(MODULE, "fetch_entry", return_value=app_entry), \
                mock.patch.object(MODULE, "discover_plugin_sources", return_value=[]):
            index = MODULE.build_index(sources, "debug")

        self.assertEqual(app_entry, index["app"])

    def test_build_catalog_groups_all_app_and_plugin_versions(self):
        sources = {
            "schemaVersion": 2,
            "app": {
                "repository": "owner/app",
                "title": "安卓工具合集",
                "description": "宿主应用",
            },
            "pluginDiscovery": {},
            "debugTag": "debug",
        }
        app_versions = [{"versionName": "2.0.0"}, {"versionName": "1.0.0"}]
        plugin_versions = [{
            "id": "sample",
            "title": "示例插件",
            "description": "说明",
            "author": "作者",
            "repositoryUrl": "https://github.test/sample",
            "versionName": "1.0.0",
        }]
        with mock.patch.object(
            MODULE,
            "discover_plugin_sources",
            return_value=[{"repository": "owner/sample", "type": "plugin"}],
        ), mock.patch.object(
            MODULE, "fetch_entries", side_effect=[app_versions, plugin_versions]
        ):
            catalog = MODULE.build_catalog(sources, "release")

        self.assertEqual("安卓工具合集", catalog["app"]["title"])
        self.assertEqual(app_versions, catalog["app"]["versions"])
        self.assertEqual("sample", catalog["plugins"][0]["id"])
        self.assertEqual(plugin_versions, catalog["plugins"][0]["versions"])

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

    def test_rejects_invalid_plugin_data_compatibility(self):
        metadata = {
            "dataCompatibility": {
                "schemaVersion": 1,
                "dataFormatVersion": 2,
                "minReadableDataFormatVersion": 3,
                "maxReadableDataFormatVersion": 2,
            }
        }

        with self.assertRaises(ValueError):
            MODULE.validate_data_compatibility(metadata)

    def test_accepts_missing_legacy_data_compatibility(self):
        MODULE.validate_data_compatibility({})

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
