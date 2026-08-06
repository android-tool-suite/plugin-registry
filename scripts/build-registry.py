#!/usr/bin/env python3
"""Build a signed-registry payload from official GitHub Releases."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_ROOT = "https://api.github.com"
CHANNELS = {"release", "debug"}


def request_json(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "android-tool-suite-plugin-registry",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def release_for_channel(
    repository: str,
    channel: str,
    debug_tag: str,
    token: str | None = None,
) -> dict[str, Any] | None:
    if channel == "release":
        endpoint = "releases/latest"
    elif channel == "debug":
        endpoint = f"releases/tags/{urllib.parse.quote(debug_tag, safe='')}"
    else:
        raise ValueError(f"unsupported channel: {channel}")
    try:
        return request_json(f"{API_ROOT}/repos/{repository}/{endpoint}", token)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def asset_by_name(release: dict[str, Any], name: str) -> dict[str, Any]:
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset
    raise ValueError(f"release {release.get('tag_name')} is missing asset {name}")


def build_release_entry(
    source: dict[str, Any],
    release: dict[str, Any],
    metadata: dict[str, Any],
    channel: str,
) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError(f"unsupported channel: {channel}")
    if metadata.get("schemaVersion") != 1:
        raise ValueError("unsupported release metadata schema")
    expected_type = source.get("type", "plugin" if source.get("id") else "app")
    if metadata.get("type") != expected_type:
        raise ValueError(f"metadata type mismatch for {source['repository']}")
    metadata_channel = metadata.get("channel", "release")
    if metadata_channel != channel:
        raise ValueError(f"metadata channel mismatch for {source['repository']}")

    artifact_names = source.get("artifactNames", {})
    artifact_name = (
        artifact_names.get(channel)
        or source.get("artifactName")
        or metadata.get("artifactName")
    )
    if not artifact_name or metadata.get("artifactName") != artifact_name:
        raise ValueError(f"metadata artifact mismatch for {source['repository']}")
    artifact = asset_by_name(release, artifact_name)
    digest = artifact.get("digest") or ""
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise ValueError(f"release asset {artifact_name} has no SHA-256 digest")
    if source.get("id") and metadata.get("id") != source["id"]:
        raise ValueError(f"plugin id mismatch for {source['repository']}")

    if channel == "release":
        if release.get("tag_name") != f"v{metadata.get('versionName')}":
            raise ValueError(f"release tag mismatch for {source['repository']}")
    else:
        expected_tag = source.get("tag", "debug")
        if release.get("tag_name") != expected_tag:
            raise ValueError(f"debug tag mismatch for {source['repository']}")
        commit_sha = metadata.get("commitSha", "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
            raise ValueError(f"debug metadata has no commit SHA for {source['repository']}")

    excluded = {"schemaVersion", "type", "artifactName"}
    entry = {key: value for key, value in metadata.items() if key not in excluded}
    entry.update(
        {
            "channel": channel,
            "releaseUrl": release["html_url"],
            "downloadUrl": artifact["browser_download_url"],
            "size": int(artifact["size"]),
            "sha256": digest.removeprefix("sha256:").lower(),
            "publishedAt": release.get("published_at", ""),
        }
    )
    return entry


def fetch_entry(
    source: dict[str, Any],
    channel: str,
    debug_tag: str,
    token: str | None = None,
) -> dict[str, Any] | None:
    release = release_for_channel(source["repository"], channel, debug_tag, token)
    if release is None:
        return None
    metadata_asset = asset_by_name(release, "release-metadata.json")
    metadata = request_json(metadata_asset["browser_download_url"], token)
    return build_release_entry(source, release, metadata, channel)


def discover_plugin_sources(
    configuration: dict[str, Any],
    token: str | None = None,
) -> list[dict[str, Any]]:
    organization = configuration.get("organization", "").strip()
    prefix = configuration.get("repositoryNamePrefix", "").strip()
    if not organization or not prefix:
        raise ValueError("plugin discovery requires organization and repositoryNamePrefix")
    excluded = set(configuration.get("excludedRepositories", []))
    sources: list[dict[str, Any]] = []
    page = 1
    while True:
        repositories = request_json(
            f"{API_ROOT}/orgs/{organization}/repos?type=public&per_page=100&page={page}",
            token,
        )
        if not isinstance(repositories, list):
            raise ValueError("GitHub organization repositories response is invalid")
        for repository in repositories:
            full_name = repository.get("full_name", "")
            name = repository.get("name", "")
            if (
                name.startswith(prefix)
                and full_name not in excluded
                and not repository.get("archived", False)
                and not repository.get("disabled", False)
                and not repository.get("fork", False)
            ):
                sources.append({"repository": full_name, "type": "plugin"})
        if len(repositories) < 100:
            break
        page += 1
    return sorted(sources, key=lambda item: item["repository"].casefold())


def build_index(
    sources: dict[str, Any],
    channel: str,
    token: str | None = None,
) -> dict[str, Any]:
    if sources.get("schemaVersion") != 2:
        raise ValueError("unsupported source schema")
    if channel not in CHANNELS:
        raise ValueError(f"unsupported channel: {channel}")
    debug_tag = sources.get("debugTag", "debug")

    app_source = dict(sources["app"])
    app_source["type"] = "app"
    if channel == "debug":
        app_source["tag"] = debug_tag
    app_entry = fetch_entry(app_source, channel, debug_tag, token)

    plugins = []
    for source in discover_plugin_sources(sources["pluginDiscovery"], token):
        if channel == "debug":
            source["tag"] = debug_tag
        entry = fetch_entry(source, channel, debug_tag, token)
        if entry is not None:
            plugins.append(entry)
    plugins.sort(key=lambda item: (item.get("title", "").casefold(), item["id"]))
    return {
        "schemaVersion": 1,
        "channel": channel,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "app": app_entry,
        "plugins": plugins,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True)
    parser.add_argument("--channel", choices=sorted(CHANNELS), required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    with open(arguments.sources, encoding="utf-8") as source_file:
        sources = json.load(source_file)
    index = build_index(sources, arguments.channel, os.environ.get("GITHUB_TOKEN"))
    output = pathlib.Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"generated {output} for {arguments.channel} with "
        f"{len(index['plugins'])} plugins"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
