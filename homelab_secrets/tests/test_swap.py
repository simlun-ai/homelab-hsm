"""Synthetic proc/sys/crypttab fixtures; no real mappings or keys are opened."""

import stat
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from homelab_secrets import swap


class SwapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contexts = ExitStack()
        self.addCleanup(self.contexts.close)
        self.real_device_number = swap.device_number
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.proc = self.root / "swaps"
        self.sys = self.root / "sys"
        self.mapping = self.sys / "252:1"
        (self.mapping / "dm").mkdir(parents=True)
        slave = self.mapping / "slaves/nvme0n1p2"
        slave.mkdir(parents=True)
        (slave / "dev").write_text("259:2\n")
        (self.mapping / "uevent").write_text("DEVNAME=dm-1\n")
        (self.mapping / "dm/name").write_text("cryptoswap\n")
        (self.mapping / "dm/uuid").write_text("CRYPT-PLAIN-cryptoswap\n")
        self.crypttab = Mock()
        self.crypttab.stat.return_value = Mock(st_uid=0, st_gid=0, st_mode=0o100644)
        self.crypttab.read_text.return_value = (
            "cryptoswap /dev/nvme0n1p2 /dev/urandom swap,initramfs\n"
        )
        self.proc.write_text(
            "Filename Type Size Used Priority\n/dev/dm-1 partition 10 5 -2\n"
        )
        for name, value in (
            ("PROC_SWAPS", self.proc),
            ("SYS_DEV_BLOCK", self.sys),
            ("CRYPTTAB", self.crypttab),
        ):
            self.contexts.enter_context(patch.object(swap, name, value))

        def lookup(path: Path) -> str:
            devices = {"/dev/dm-1": "252:1", "/dev/nvme0n1p2": "259:2"}
            if str(path) not in devices:
                raise OSError("Unknown fixture device")
            return devices[str(path)]

        self.device = self.contexts.enter_context(
            patch.object(swap, "device_number", side_effect=lookup)
        )

    def test_user_random_key_mapping_is_allowed(self) -> None:
        swap.require_safe_swap()

    def test_root_group_write_is_trusted(self) -> None:
        for gid, mode in ((0, 0o100664), (0, 0o100660), (1000, 0o100644)):
            with self.subTest(gid=gid, mode=mode):
                self.crypttab.stat.return_value = Mock(
                    st_uid=0, st_gid=gid, st_mode=mode
                )
                swap.require_safe_swap()

    def test_no_swap_needs_no_crypttab_or_sysfs(self) -> None:
        self.proc.write_text("Filename Type Size Used Priority\n")
        swap.require_safe_swap()
        self.crypttab.read_text.assert_not_called()

    def test_zram_requires_no_writeback(self) -> None:
        (self.mapping / "uevent").write_text("DEVNAME=zram0\n")
        backing = self.mapping / "backing_dev"
        backing.write_text("none\n")
        swap.require_safe_swap()
        backing.write_text("/dev/sda\n")
        with self.assertRaises(swap.UnsafeSwapError):
            swap.require_safe_swap()
        backing.unlink()
        with self.assertRaises(swap.UnsafeSwapError):
            swap.require_safe_swap()

    def test_missing_or_noncrypt_mapping_is_rejected(self) -> None:
        (self.mapping / "dm/uuid").write_text("LVM-public\n")
        with self.assertRaises(swap.UnsafeSwapError):
            swap.require_safe_swap()
        (self.mapping / "dm/uuid").unlink()
        with self.assertRaises(swap.UnsafeSwapError):
            swap.require_safe_swap()

    def test_bad_configurations_are_rejected(self) -> None:
        entries = [
            "cryptoswap /dev/nvme0n1p2 /etc/key swap",
            "cryptoswap /dev/nvme0n1p2 none swap",
            "other /dev/nvme0n1p2 /dev/urandom swap",
            "cryptoswap /dev/nvme0n1p2 /dev/urandom initramfs",
            "cryptoswap /dev/nvme0n1p2 /dev/urandom swap,cipher=cipher_null",
            "cryptoswap /dev/nvme0n1p2 /dev/urandom swap,keyscript=custom",
            "cryptoswap /dev/nvme0n1p2 /dev/urandom swap\n" * 2,
        ]
        for entry in entries:
            with self.subTest(entry=entry):
                self.crypttab.read_text.return_value = entry
                with self.assertRaises(swap.UnsafeSwapError):
                    swap.require_safe_swap()

    def test_mapping_source_must_match(self) -> None:
        (self.mapping / "slaves/nvme0n1p2/dev").write_text("259:3\n")
        with self.assertRaises(swap.UnsafeSwapError):
            swap.require_safe_swap()

    def test_untrusted_or_unreadable_crypttab_is_rejected(self) -> None:
        for uid, gid, mode in (
            (1000, 0, 0o100644),
            (0, 0, 0o100666),
            (0, 1000, 0o100664),
        ):
            self.crypttab.stat.return_value = Mock(st_uid=uid, st_gid=gid, st_mode=mode)
            with self.assertRaises(swap.UnsafeSwapError):
                swap.require_safe_swap()
        self.crypttab.stat.side_effect = PermissionError
        with self.assertRaises(swap.UnsafeSwapError):
            swap.require_safe_swap()

    def test_inventory_files_and_mixed_swap_are_rejected(self) -> None:
        for contents in (
            "",
            "invalid",
            "Filename Type Size Used Priority\n/swapfile file 10 0 -2\n",
            self.proc.read_text() + "/unverified partition 10 0 -3\n",
        ):
            self.proc.write_text(contents)
            with self.assertRaises(swap.UnsafeSwapError):
                swap.require_safe_swap()

    def test_block_lookup_rejects_regular_files(self) -> None:
        with patch.object(Path, "stat", return_value=Mock(st_mode=stat.S_IFREG)):
            with self.assertRaises(swap.UnsafeSwapError):
                self.real_device_number(Path("/swapfile"))
