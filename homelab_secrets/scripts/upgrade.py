"""Refresh pins and export every Bake bundle directly into the checkout."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAKE = ["docker", "buildx", "bake", "--file", "docker-bake.hcl", "--progress=plain"]


def upgrade() -> None:
    # Ask Bake for the targets instead of maintaining a second platform matrix.
    plan = subprocess.run(
        BAKE + ["--print", "upgrade"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    bundles: set[Path] = set()
    for target in json.loads(plan.stdout)["target"].values():
        minor = target["args"]["EXPECTED_PYTHON"]
        if not re.fullmatch(r"3\.\d+", minor) or target["platforms"] != ["linux/amd64"]:
            raise RuntimeError("Unsupported upgrade target in docker-bake.hcl")
        bundles.add(ROOT / "offline" / f"cpython-{minor}-linux-x86_64")
    if not bundles:
        raise RuntimeError("Bake did not define any upgrade targets")
    subprocess.run(BAKE + ["refresh-pins"], cwd=ROOT, check=True)
    # Local exporters merge directories. Remove old sets so obsolete wheels go away.
    # There is deliberately no rollback: Git retains the previous pins and bundles.
    for bundle in sorted(bundles):
        if bundle.exists():
            shutil.rmtree(bundle)
    subprocess.run(BAKE + ["upgrade"], cwd=ROOT, check=True)
    print("Updated pyproject.toml and offline/. Running make ci next.", flush=True)


if __name__ == "__main__":
    try:
        upgrade()
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        sys.exit(
            f"Dependency upgrade failed: {error}\n"
            "Changes were left in place; inspect, fix, or revert them with Git."
        )
