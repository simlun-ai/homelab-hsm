"""Exercise the upgrade workflow's destructive/partial-failure behavior with fake Bake."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "dependency_upgrade", Path(__file__).resolve().parents[1] / "scripts/upgrade.py"
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class UpgradeTests(unittest.TestCase):
    def test_refreshes_pins_removes_obsolete_wheels_and_preserves_other_targets(self):
        self.exercise(fail=False)

    def test_failed_build_leaves_updated_pins_and_partial_bundles_in_place(self):
        self.exercise(fail=True)

    def exercise(self, *, fail):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "pyproject.toml"
            project.write_text("old pins")
            bundle = root / "offline/cpython-3.10-linux-x86_64"
            bundle.mkdir(parents=True)
            (bundle / "obsolete.whl").write_text("old wheel")
            unrelated = root / "offline/cpython-3.11-linux-x86_64"
            unrelated.mkdir()
            (unrelated / "keep").write_text("keep")
            plan = {
                "target": {
                    "upgrade-jammy": {
                        "args": {"EXPECTED_PYTHON": "3.10"},
                        "platforms": ["linux/amd64"],
                    }
                }
            }

            def bake(command, **kwargs):
                if "--print" in command:
                    return subprocess.CompletedProcess(
                        command, 0, stdout=json.dumps(plan)
                    )
                if command[-1] == "refresh-pins":
                    self.assertTrue((bundle / "obsolete.whl").exists())
                    project.write_text("new pins")
                else:
                    self.assertFalse(bundle.exists())
                    bundle.mkdir()
                    (bundle / "new.whl").write_text("new wheel")
                    if fail:
                        raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            with (
                patch.object(upgrade, "ROOT", root),
                patch.object(upgrade.subprocess, "run", side_effect=bake),
            ):
                if fail:
                    with self.assertRaises(subprocess.CalledProcessError):
                        upgrade.upgrade()
                else:
                    upgrade.upgrade()
            self.assertEqual(project.read_text(), "new pins")
            self.assertFalse((bundle / "obsolete.whl").exists())
            self.assertTrue((bundle / "new.whl").exists())
            self.assertTrue((unrelated / "keep").exists())
