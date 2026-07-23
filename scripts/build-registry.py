#!/usr/bin/env python3
"""Build the signed-registry payload from official GitHub Releases."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any

API_ROOT = "https://api.github.com"


def request_json(url: str, token: str | None = None) -> dict[str, Any]:
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


def latest_release(repository: str, token: str | None = None) -> dict[str, Any] | None:
    try:
        return request_json(f"{API_ROOT}/repos/{repository}/releases/latest", token)
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
) -> dict[str, Any]:
    if metadata.get("schemaVersion") != 1:
        raise ValueError("unsupported release metadata schema")
    expected_type = "plugin" if source.get("id") else "app"
    if metadata.get("type") != expected_type:
        raise ValueError(f"metadata type mismatch for {source['repository']}")
    artifact_name = source["artifactName"]
    if metadata.get("artifactName") != artifact_name:
        raise ValueError(f"metadata artifact mismatch for {source['repository']}")
    artifact = asset_by_name(release, artifact_name)
    digest = artifact.get("digest") or ""
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise ValueError(f"release asset {artifact_name} has no SHA-256 digest")
    if source.get("id") and metadata.get("id") != source["id"]:
        raise ValueError(f"plugin id mismatch for {source['repository']}")
    if release.get("tag_name") != f"v{metadata.get('versionName')}":
        raise ValueError(f"release tag mismatch for {source['repository']}")

    excluded = {"schemaVersion", "type", "artifactName"}
    entry = {key: value for key, value in metadata.items() if key not in excluded}
    entry.update(
        {
            "releaseUrl": release["html_url"],
            "downloadUrl": artifact["browser_download_url"],
            "size": int(artifact["size"]),
            "sha256": digest.removeprefix("sha256:").lower(),
            "publishedAt": release.get("published_at", ""),
        }
    )
    return entry


def fetch_entry(source: dict[str, Any], token: str | None = None) -> dict[str, Any] | None:
    release = latest_release(source["repository"], token)
    if release is None:
        return None
    metadata_asset = asset_by_name(release, "release-metadata.json")
    metadata = request_json(metadata_asset["browser_download_url"])
    return build_release_entry(source, release, metadata)


def build_index(sources: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    if sources.get("schemaVersion") != 1:
        raise ValueError("unsupported source schema")
    app_entry = fetch_entry(sources["app"], token)
    plugins = []
    for source in sources.get("plugins", []):
        entry = fetch_entry(source, token)
        if entry is not None:
            plugins.append(entry)
    plugins.sort(key=lambda item: (item.get("title", "").casefold(), item["id"]))
    return {
        "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "app": app_entry,
        "plugins": plugins,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    with open(arguments.sources, encoding="utf-8") as source_file:
        sources = json.load(source_file)
    index = build_index(sources, os.environ.get("GITHUB_TOKEN"))
    output = pathlib.Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"generated {output} with {len(index['plugins'])} plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
