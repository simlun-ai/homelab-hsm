"""Build online once; install the committed wheel bundle without network access."""
import email
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import sysconfig
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = ROOT / "offline"


def bundle_key(info):
    return f"{info['implementation']}-{info['python']}-{info['platform']}"


def select_bundle():
    preferred = BUNDLES / bundle_key(target())
    if preferred.is_dir():
        return preferred
    candidates = [p.parent for p in sorted(BUNDLES.glob("*/target.json"))
                  if all(json.loads(p.read_text())[key] == target()[key]
                         for key in ("platform", "implementation"))]
    if not candidates:
        raise RuntimeError("No bundle for this platform; run make build online first")
    return candidates[0]


def run(*args, cwd=ROOT, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def source_digest():
    digest = hashlib.sha256()
    for path in [ROOT / "pyproject.toml", *sorted((ROOT / "src").rglob("*.py"))]:
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def wheel_libc(wheels):
    """Inspect ELF symbol requirements instead of requiring the builder’s libc."""
    required = (2, 2, 5)
    with tempfile.TemporaryDirectory(dir=ROOT / ".build") as directory:
        elf = Path(directory) / "extension.so"
        for wheel in wheels.glob("*.whl"):
            with zipfile.ZipFile(wheel) as archive:
                for name in archive.namelist():
                    if not name.endswith(".so"):
                        continue
                    elf.write_bytes(archive.read(name))
                    result = subprocess.run(["readelf", "--version-info", str(elf)],
                                            check=True, capture_output=True, text=True)
                    for version in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", result.stdout):
                        required = max(required, tuple(map(int, version.split("."))))
    return ["glibc", ".".join(map(str, required))]


def target():
    return {
        "platform": sysconfig.get_platform(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "implementation": sys.implementation.name,
        "libc": list(platform.libc_ver()),
    }


def check_python():
    if sys.platform != "linux" or not (3, 10) <= sys.version_info[:2] < (3, 15):
        raise RuntimeError("Use Linux with Python 3.10–3.14")


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
    destination = BUNDLES / bundle_key(target())
    BUNDLES.mkdir(exist_ok=True)
    # Stage outside offline/: a failed build leaves the previous bundle intact.
    work = ROOT / ".build"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work, ignore_cleanup_errors=True) as directory:
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
        info = {**target(), "source_sha256": source_digest()}
        info["libc"] = wheel_libc(wheels)
        (bundle / "target.json").write_text(json.dumps(info, indent=2) + "\n")
        verification = staging / "verification"
        venv.EnvBuilder(with_pip=True).create(verification)
        install_wheels(verification / "bin/python", bundle)
        run(verification / "bin/python", "-I", "-B", "-m", "unittest",
            "discover", "-s", "tests", "-v")
        previous = staging / "previous"
        if destination.exists():
            destination.rename(previous)
        try:
            bundle.rename(destination)
        except BaseException:
            if previous.exists():
                previous.rename(destination)
            raise
    print(f"Replaced {destination.relative_to(ROOT)}/. Other targets preserved.\n"
          "Commit the complete bundle with the source changes.")


def install():
    bundle = select_bundle()
    recorded = json.loads((bundle / "target.json").read_text())
    current = target()
    for key in ("platform", "implementation"):
        if current[key] != recorded[key]:
            raise RuntimeError(f"Bundle requires {key}={recorded[key]}; found {current[key]}")
    if current["python"] != recorded["python"]:
        print(f"Bundle built with Python {recorded['python']}; trying {current['python']} "
              "with offline wheel compatibility checks and tests.", file=sys.stderr)
    family, version = current["libc"]
    required_family, required_version = recorded["libc"]
    if family != required_family or tuple(map(int, version.split("."))) < tuple(
            map(int, required_version.split("."))):
        raise RuntimeError(f"Bundle requires {required_family} >= {required_version}")
    if recorded["source_sha256"] != source_digest():
        raise RuntimeError("Bundle does not match the source/pyproject.toml; run make build online")
    environment = ROOT / ".venv"
    if environment.exists():
        # Verify an existing environment before mutating it.
        run(environment / "bin/python", "-I", "-c",
            f"import sys; assert sys.version_info[:2] == {sys.version_info[:2]!r}, "
            "'Existing .venv uses another Python version; remove it and retry'")
    else:
        venv.EnvBuilder(with_pip=True).create(environment)
    install_wheels(environment / "bin/python", bundle)
    run(environment / "bin/python", "-I", "-B", "-m", "unittest",
        "discover", "-s", "tests", "-v")
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
