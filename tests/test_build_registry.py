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
            "minAndroidApi": 26,
            "artifactName": "sample.atsplugin",
        }

        entry = MODULE.build_release_entry(source, release, metadata, "release")

        self.assertEqual("sample", entry["id"])
        self.assertEqual("release", entry["channel"])
        self.assertEqual("v1.0.0", entry["tagName"])
        self.assertEqual("ab" * 32, entry["sha256"])
        self.assertEqual(12, entry["size"])
        self.assertEqual(26, entry["minAndroidApi"])
        self.assertNotIn("artifactName", entry)

    def test_rejects_invalid_minimum_android_api(self):
        source = {"id": "sample", "repository": "owner/sample", "artifactName": "sample.atsplugin"}
        release = {
            "tag_name": "v1.0.0",
            "html_url": "https://github.test/release",
            "published_at": "2026-09-01T00:00:00Z",
            "assets": [{
                "name": "sample.atsplugin",
                "browser_download_url": "https://github.test/sample.atsplugin",
                "size": 12,
                "digest": "sha256:" + "ab" * 32,
            }],
        }
        metadata = {
            "schemaVersion": 1,
            "type": "plugin",
            "id": "sample",
            "title": "Sample",
            "versionName": "1.0.0",
            "versionCode": 1,
            "minAndroidApi": 23,
            "artifactName": "sample.atsplugin",
        }
        with self.assertRaisesRegex(ValueError, "minAndroidApi"):
            MODULE.build_release_entry(source, release, metadata, "release")

    def test_release_history_filters_drafts_and_other_tags(self):
        releases = [
            {"tag_name": "v2.0.0", "draft": False, "prerelease": False},
            {"tag_name": "v1.0.0", "draft": True, "prerelease": False},
            {"tag_name": "debug", "draft": False, "prerelease": True},
            {"tag_name": "plugin-sdk-v1.0.0", "draft": False, "prerelease": False},
        ]
        with mock.patch.object(MODULE, "request_json", return_value=releases):
            result = MODULE.releases_for_channel("owner/app", "release")

        self.assertEqual(["v2.0.0"], [release["tag_name"] for release in result])

    def test_missing_formal_release_does_not_fall_back_to_debug(self):
        with mock.patch.object(MODULE, "release_for_channel", return_value=None), \
                mock.patch.object(MODULE, "fetch_entries") as fetch_entries:
            self.assertIsNone(MODULE.fetch_entry({"repository": "owner/app"}, "release"))
        fetch_entries.assert_not_called()

    def test_fetch_entry_keeps_formal_release_asset_validation_strict(self):
        release = {"tag_name": "v1.0.0", "assets": []}

        with mock.patch.object(
            MODULE, "release_for_channel", return_value=release
        ):
            with self.assertRaises(MODULE.MissingReleaseAssetError):
                MODULE.fetch_entry(
                    {"repository": "owner/app"}, "release"
                )


    def test_build_release_index_includes_app(self):
        sources = {
            "schemaVersion": 2,
            "app": {"repository": "owner/app"},
            "pluginDiscovery": {},
        }
        app_entry = {"packageName": "com.androidtoolsuite.app"}
        with mock.patch.object(MODULE, "fetch_entry", return_value=app_entry), \
                mock.patch.object(MODULE, "discover_plugin_sources", return_value=[]):
            index = MODULE.build_index(sources, "release")

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

    def test_accepts_declared_v0_read_compatibility(self):
        MODULE.validate_data_compatibility({
            "dataCompatibility": {
                "schemaVersion": 1,
                "dataFormatVersion": 1,
                "minReadableDataFormatVersion": 0,
                "maxReadableDataFormatVersion": 1,
            }
        })

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
        with self.assertRaisesRegex(ValueError, "channel mismatch"):
            MODULE.build_release_entry(
                {"repository": "owner/sample", "type": "plugin"}, {},
                {"schemaVersion": 1, "type": "plugin", "channel": "debug"}, "release"
            )

    def test_rejects_retired_channels_before_network_access(self):
        sources = {"schemaVersion": 2}
        with mock.patch.object(MODULE, "request_json") as request:
            for channel in ("debug", "preview", ""):
                calls = [
                    lambda: MODULE.release_for_channel("owner/app", channel),
                    lambda: MODULE.releases_for_channel("owner/app", channel),
                    lambda: MODULE.fetch_entry({"repository": "owner/app"}, channel),
                    lambda: MODULE.fetch_entries({"repository": "owner/app"}, channel),
                    lambda: MODULE.build_release_entry({}, {}, {}, channel),
                    lambda: MODULE.build_index(sources, channel),
                    lambda: MODULE.build_catalog(sources, channel),
                ]
                for call in calls:
                    with self.subTest(channel=channel, call=call), self.assertRaisesRegex(ValueError, "unsupported channel"):
                        call()
            request.assert_not_called()

    def test_formal_history_excludes_all_debug_tag_formats(self):
        releases = [
            {"tag_name": tag, "prerelease": prerelease}
            for tag in ("debug", "debug-" + "a" * 40, "debug-v2.0.0", "v2.0.0")
            for prerelease in (True, False)
        ]
        with mock.patch.object(MODULE, "request_json", return_value=releases):
            selected = MODULE.releases_for_channel("owner/app", "release")
        self.assertEqual([{"tag_name": "v2.0.0", "prerelease": False}], selected)

    def test_formal_history_preserves_versions_and_sorts_newest_first(self):
        entries = [
            {"tagName": "v1.0.0", "publishedAt": "2026-08-01", "versionCode": 1},
            {"tagName": "v2.0.0", "publishedAt": "2026-09-01", "versionCode": 2},
        ]
        with mock.patch.object(MODULE, "releases_for_channel", return_value=[{}, {}]), \
                mock.patch.object(MODULE, "load_release_entry", side_effect=entries):
            actual = MODULE.fetch_entries({"repository": "owner/app"}, "release")
        self.assertEqual(list(reversed(entries)), actual)

    def test_formal_history_missing_asset_fails_without_skipping(self):
        with mock.patch.object(MODULE, "releases_for_channel", return_value=[{"tag_name": "v1.0.0", "assets": []}]):
            with self.assertRaises(MODULE.MissingReleaseAssetError):
                MODULE.fetch_entries({"repository": "owner/app"}, "release")

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
