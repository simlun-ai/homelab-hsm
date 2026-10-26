"""Exercise installed entrypoint processes with public fake-key payloads only."""

import base64
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from collections.abc import Sequence

ID = "homelab/v1/test/credential/container/r1"
BASE = [sys.executable, "-m", "homelab_secrets.container"]


def cli(
    command: str,
    data: bytes = b"",
    *,
    key_id: str = ID,
    extra: Sequence[str] = (),
    fake: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        BASE
        + [
            command,
            "--key-id",
            key_id,
            *(["--fake-yubikey"] if fake else []),
            "--stdin",
            "--stdout",
            *extra,
        ],
        input=data,
        capture_output=True,
    )


class ImageTests(unittest.TestCase):
    def test_runtime_is_nonroot_system_python_without_pip_or_pcsc(self) -> None:
        self.assertNotEqual(os.getuid(), 0)
        self.assertEqual(sys.prefix, sys.base_prefix)
        self.assertEqual(sys.prefix, "/usr")
        self.assertIsNone(importlib.util.find_spec("pip"))
        with self.assertRaises(OSError):
            ctypes.CDLL("libpcsclite.so.1")

    def test_help_and_dispatch_errors(self) -> None:
        for command in ("wrap", "unwrap"):
            result = subprocess.run(BASE + [command, "--help"], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(("homelab-" + command).encode(), result.stdout)
        self.assertEqual(
            subprocess.run(BASE + ["unknown"], capture_output=True).returncode, 2
        )

    def test_separate_process_binary_round_trips(self) -> None:
        for payload in (b"", bytes(range(256)) * 32, b"public dummy\x00\xff\n"):
            wrapped = cli("wrap", payload)
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr)
            self.assertIn(b"PUBLIC key", wrapped.stderr)
            self.assertEqual(json.loads(wrapped.stdout)["root_key"], "golden-fake-1")
            plain = cli("unwrap", wrapped.stdout)
            self.assertEqual(plain.returncode, 0, plain.stderr)
            self.assertEqual(plain.stdout, payload)
            self.assertIn(b"PUBLIC key", plain.stderr)

    def test_tampering_releases_no_plaintext(self) -> None:
        record = json.loads(cli("wrap", b"public dummy").stdout)
        ciphertext = bytearray(base64.b64decode(record["ciphertext"]))
        ciphertext[0] ^= 1
        record["ciphertext"] = base64.b64encode(ciphertext).decode()
        result = cli("unwrap", json.dumps(record).encode())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_wrong_context_and_reserved_root_fail(self) -> None:
        record = cli("wrap", b"public dummy").stdout
        cases = [
            cli("unwrap", record, key_id=ID.replace("container", "other")),
            cli("unwrap", record, extra=["--root-key", "golden-1"]),
            cli("unwrap", record, fake=False, extra=["--root-key", "golden-fake-1"]),
            cli("unwrap", record, fake=False, extra=["--root-key", "golden-1"]),
        ]
        for result in cases:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_bounds_and_malformed_input(self) -> None:
        for command, data in [
            ("wrap", b"x" * (1024 * 1024 + 1)),
            ("unwrap", b"x" * (2 * 1024 * 1024 + 1)),
            ("unwrap", b"{}"),
        ]:
            result = cli(command, data)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
