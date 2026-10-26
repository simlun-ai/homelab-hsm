"""Refresh shared pins to stable PyPI releases supporting every target Python."""

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

import tomllib
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


def latest_compatible(releases, pythons):
    candidates = []
    for label, files in releases.items():
        try:
            version = Version(label)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        available = [file for file in files if not file.get("yanked", False)]
        if available and all(
            any(
                SpecifierSet(file.get("requires_python") or "").contains(python)
                for file in available
            )
            for python in pythons
        ):
            candidates.append(version)
    if not candidates:
        raise RuntimeError("No stable, non-yanked release supports every target Python")
    return str(max(candidates))


def refresh(text, pythons, fetch):
    project = tomllib.loads(text)
    updated = text
    cache = {}
    for section, field in [("project", "dependencies"), ("build-system", "requires")]:
        for original in project[section][field]:
            requirement = Requirement(original)
            if requirement.url:
                raise RuntimeError(
                    f"Cannot upgrade URL requirement: {requirement.name}"
                )
            if requirement.name not in cache:
                cache[requirement.name] = latest_compatible(
                    fetch(requirement.name), pythons
                )
            requirement.specifier = SpecifierSet("==" + cache[requirement.name])
            replacement = str(requirement)
            # Keep the rest of pyproject.toml unchanged. Refuse ambiguous edits.
            literals = [json.dumps(original), "'" + original + "'"]
            matches = [literal for literal in literals if updated.count(literal) == 1]
            if len(matches) != 1:
                raise RuntimeError(
                    f"Cannot locate a unique TOML literal for {original}"
                )
            updated = updated.replace(matches[0], json.dumps(replacement), 1)
            print(f"{original} -> {replacement}", flush=True)
    tomllib.loads(updated)  # Validate before writing, without changing our own version.
    return updated


def fetch_releases(name):
    url = "https://pypi.org/pypi/" + urllib.parse.quote(name, safe="") + "/json"
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)["releases"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pythons", required=True, type=json.loads)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = refresh(Path("pyproject.toml").read_text(), args.pythons, fetch_releases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)
