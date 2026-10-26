"""Build online once; install the committed wheel bundle without network access."""
import ctypes
import email
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "offline"


def run(*args, cwd=ROOT, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def target():
    return {
        "platform": sysconfig.get_platform(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "implementation": sys.implementation.name,
        "libc": list(platform.libc_ver()),
    }


def check_python():
    if sys.platform != "linux" or not (3, 11) <= sys.version_info[:2] < (3, 15):
        raise RuntimeError("Use Linux with Python 3.11–3.14")


def install_wheels(python, bundle):
    # Isolate pip from user settings, caches, indexes, and source builds.
    run(python, "-I", "-m", "pip", "--isolated", "--disable-pip-version-check",
        "install", "--no-index", "--no-cache-dir", "--only-binary=:all:",
        "--require-hashes", "--force-reinstall", "--find-links", bundle / "wheels",
        "-r", bundle / "requirements.lock")
    run(python, "-I", "-m", "pip", "--isolated", "check")
    for command in ("homelab-wrap", "homelab-unwrap"):
        run(Path(python).parent / command, "--help")


def build():
    # Stage outside offline/: a failed build leaves the previous bundle intact.
    work = ROOT / ".build"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        staging = Path(directory)
        builder = staging / "builder"
        venv.EnvBuilder(with_pip=True).create(builder)
        python = builder / "bin/python"
        bundle = staging / "offline"
        wheels = bundle / "wheels"
        wheels.mkdir(parents=True)
        # Build isolation installs the backend pinned in pyproject.toml.
        run(python, "-I", "-m", "pip", "--isolated", "--disable-pip-version-check",
            "wheel", "--no-cache-dir", "--wheel-dir", wheels, ROOT,
            env={**os.environ, "TMPDIR": str(staging)})
        requirements = []
        for wheel in sorted(wheels.glob("*.whl")):
            with zipfile.ZipFile(wheel) as archive:
                metadata_path, = [name for name in archive.namelist()
                                  if name.endswith(".dist-info/METADATA")]
                metadata = email.message_from_bytes(archive.read(metadata_path))
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            requirements.append(
                f"{metadata['Name']}=={metadata['Version']} --hash=sha256:{digest}\n")
        (bundle / "requirements.lock").write_text("".join(requirements))
        (bundle / "target.json").write_text(json.dumps(target(), indent=2) + "\n")
        verification = staging / "verification"
        venv.EnvBuilder(with_pip=True).create(verification)
        install_wheels(verification / "bin/python", bundle)
        run(verification / "bin/python", "-I", "-B", "-m", "unittest",
            "discover", "-s", "tests", "-v")
        previous = staging / "previous"
        if BUNDLE.exists():
            BUNDLE.rename(previous)
        try:
            bundle.rename(BUNDLE)
        except BaseException:
            if previous.exists():
                previous.rename(BUNDLE)
            raise
    print("Replaced offline/. Commit the complete bundle with the source changes.")


def install():
    recorded = json.loads((BUNDLE / "target.json").read_text())
    current = target()
    for key in ("platform", "python", "implementation"):
        if current[key] != recorded[key]:
            raise RuntimeError(f"Bundle requires {key}={recorded[key]}; found {current[key]}")
    family, version = current["libc"]
    required_family, required_version = recorded["libc"]
    if family != required_family or tuple(map(int, version.split("."))) < tuple(
            map(int, required_version.split("."))):
        raise RuntimeError(f"Bundle requires {required_family} >= {required_version}")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    expected = f"{project['name']}=={project['version']} "
    if not any(line.startswith(expected) for line in
               (BUNDLE / "requirements.lock").read_text().splitlines()):
        raise RuntimeError("Bundle version differs from pyproject.toml; run make build online")
    try:
        ctypes.CDLL("libpcsclite.so.1")
    except OSError:
        raise RuntimeError("Install the PC/SC runtime (libpcsclite1 on Ubuntu) first") from None
    environment = ROOT / ".venv"
    if environment.exists():
        # Verify an existing environment before mutating it.
        run(environment / "bin/python", "-I", "-c",
            f"import sys; assert sys.version_info[:2] == {sys.version_info[:2]!r}, "
            "'Existing .venv uses another Python version; remove it and retry'")
    else:
        venv.EnvBuilder(with_pip=True).create(environment)
    install_wheels(environment / "bin/python", BUNDLE)
    print("\nInstallation complete.\n\nActivate the environment:\n"
          "  source .venv/bin/activate\n\nThen use:\n"
          "  homelab-wrap\n  homelab-unwrap")


if __name__ == "__main__":
    os.chdir(ROOT)
    try:
        check_python()
        {"build": build, "install": install}[sys.argv[1]]()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"Offline packaging failed: {error}")
