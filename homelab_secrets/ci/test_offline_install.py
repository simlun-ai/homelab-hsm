"""Install and refresh externally without changing an imported source checkout."""

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in ROOT.rglob("*")
        if path.is_file()
    }


def main() -> None:
    before = snapshot()
    with tempfile.TemporaryDirectory() as directory:
        environment = Path(directory) / "hsm"
        for _ in range(2):
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts/offline.py"),
                    "install",
                    "--venv",
                    str(environment),
                ],
                check=True,
            )
            if snapshot() != before:
                raise RuntimeError("Offline installation modified the source checkout")
        subprocess.run([str(environment / "bin/homelab-hsm"), "--help"], check=True)


if __name__ == "__main__":
    main()
