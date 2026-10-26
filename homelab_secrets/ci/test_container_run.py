"""Check Docker's actual entrypoint and binary streams, with no volumes or devices."""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from image_metadata import image_metadata

IMAGE = image_metadata()["tag"]
ID = "homelab/v1/test/credential/container/r1"
DOCKER = [
    "docker",
    "run",
    "--rm",
    "-i",
    "--network=none",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
]


class DockerRunTests(unittest.TestCase):
    def test_entrypoint_help(self) -> None:
        for command in ("wrap", "unwrap"):
            result = subprocess.run(
                DOCKER + [IMAGE, command, "--help"], capture_output=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(("homelab-" + command).encode(), result.stdout)

    def test_nonroot_default(self) -> None:
        result = subprocess.run(
            DOCKER
            + [
                "--entrypoint",
                "/usr/bin/python3",
                IMAGE,
                "-c",
                "import os; assert os.getuid() != 0",
            ],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_binary_round_trip_without_volumes_or_usb(self) -> None:
        payload = bytes(range(256)) * 8 + b"\x00\n"
        options = ["--fake-yubikey", "--stdin", "--stdout", "--key-id", ID]
        wrapped = subprocess.run(
            DOCKER + [IMAGE, "wrap", *options], input=payload, capture_output=True
        )
        self.assertEqual(wrapped.returncode, 0, wrapped.stderr)
        plain = subprocess.run(
            DOCKER + [IMAGE, "unwrap", *options],
            input=wrapped.stdout,
            capture_output=True,
        )
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(plain.stdout, payload)
        self.assertIn(b"PUBLIC key", wrapped.stderr)
        self.assertIn(b"PUBLIC key", plain.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
