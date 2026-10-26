"""Build/load the validated local image and optionally scan it with Grype."""

import argparse
import os
import shutil
import subprocess

from image_metadata import image_metadata
from offline import ROOT

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true", help="show a Grype report")
    args = parser.parse_args()
    if args.scan and shutil.which("grype") is None:
        parser.error("grype is required for scanning; install it and add it to PATH")
    info = image_metadata()
    subprocess.run(
        [
            "docker",
            "buildx",
            "bake",
            "--file",
            "docker-bake.hcl",
            "--progress=plain",
            "container-image",
        ],
        cwd=ROOT,
        check=True,
        env={**os.environ, "IMAGE_TAG": info["tag"]},
    )
    print(f"Built local image {info['tag']}", flush=True)
    if args.scan:
        subprocess.run(
            ["grype", f"docker:{info['tag']}", "--output", "table"],
            cwd=ROOT,
            check=True,
        )
