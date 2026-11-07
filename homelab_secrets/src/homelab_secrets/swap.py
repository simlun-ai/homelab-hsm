"""Read-only Linux swap admission; never inspect encryption keys or dm tables."""

import os
import re
import stat
from pathlib import Path

PROC_SWAPS = Path("/proc/swaps")
SYS_DEV_BLOCK = Path("/sys/dev/block")
CRYPTTAB = Path("/etc/crypttab")


class UnsafeSwapError(RuntimeError):
    """Public preflight failure, safe to display before handling secrets."""


def device_number(path: Path) -> str:
    info = path.stat()
    if not stat.S_ISBLK(info.st_mode):
        raise UnsafeSwapError("Swap files and non-block swap paths are unverified")
    return f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"


def _source_path(source: str) -> Path:
    for prefix, directory in (("UUID=", "by-uuid"), ("PARTUUID=", "by-partuuid")):
        if source.startswith(prefix):
            identifier = source[len(prefix) :]
            if not identifier or "/" in identifier:
                raise UnsafeSwapError("Unverified crypttab source identifier")
            return Path("/dev/disk") / directory / identifier
    if not source.startswith("/dev/"):
        raise UnsafeSwapError("Unverified crypttab source path")
    return Path(source)


def _random_key_mapping(device: Path) -> bool:
    name = (device / "dm/name").read_text().strip()
    uuid = (device / "dm/uuid").read_text().strip()
    if uuid != f"CRYPT-PLAIN-{name}":
        return False
    info = CRYPTTAB.stat()
    if (
        info.st_uid != 0
        or info.st_mode & 0o002
        or (info.st_mode & 0o020 and info.st_gid != 0)
    ):
        raise UnsafeSwapError(
            "crypttab must be root-owned, not world writable, and writable only by root/root group"
        )
    entries: list[list[str]] = []
    for line in CRYPTTAB.read_text().splitlines():
        fields = line.split()
        if fields and not fields[0].startswith("#") and fields[0] == name:
            entries.append(fields)
    if len(entries) != 1 or len(entries[0]) != 4:
        return False
    _, source, key, options = entries[0]
    settings = set(options.split(","))
    # Deliberately small supported policy. Unrecognized key/cipher overrides
    # must not silently weaken the random-key configuration.
    allowed = {"swap", "initramfs", "plain", "noearly", "nofail"}
    for setting in settings - allowed:
        if not re.fullmatch(r"cipher=aes-(?:xts-plain64|cbc-essiv:sha256)", setting):
            if not re.fullmatch(r"size=(?:256|512)", setting):
                return False
    if "swap" not in settings or key not in ("/dev/urandom", "/dev/random"):
        return False
    slaves = list((device / "slaves").iterdir())
    return len(slaves) == 1 and (
        slaves[0] / "dev"
    ).read_text().strip() == device_number(_source_path(source))


def require_safe_swap() -> None:
    """Accept every active area only when its storage protection is recognized."""
    try:
        lines = PROC_SWAPS.read_text().splitlines()
        if not lines or lines[0].split() != [
            "Filename",
            "Type",
            "Size",
            "Used",
            "Priority",
        ]:
            raise UnsafeSwapError("Cannot verify the active swap inventory")
        for line in lines[1:]:
            fields = line.split()
            if len(fields) != 5 or fields[1] != "partition":
                raise UnsafeSwapError(
                    "Swap files or malformed swap entries are unverified"
                )
            device = SYS_DEV_BLOCK / device_number(Path(fields[0]))
            # zram is allowed only with explicit evidence of no backing device.
            uevent = (device / "uevent").read_text().splitlines()
            if any(re.fullmatch(r"DEVNAME=zram[0-9]+", item) for item in uevent):
                if (device / "backing_dev").read_text().strip() != "none":
                    raise UnsafeSwapError("zram writeback is not allowed")
            elif not _random_key_mapping(device):
                raise UnsafeSwapError(
                    "Active swap lacks verified random-key encryption"
                )
    except UnsafeSwapError:
        raise
    except (OSError, ValueError):
        raise UnsafeSwapError(
            "Cannot verify active swap protection; refusing secret operation"
        ) from None
