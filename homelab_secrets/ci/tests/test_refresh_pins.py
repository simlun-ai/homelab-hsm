import importlib.util
import unittest
from pathlib import Path

import tomllib

spec = importlib.util.spec_from_file_location(
    "refresh_pins", Path(__file__).resolve().parents[2] / "scripts/refresh_pins.py"
)
pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pins)


class RefreshPinsTests(unittest.TestCase):
    def test_latest_release_must_support_every_python_and_not_be_yanked(self):
        releases = {
            "1.0": [{"requires_python": ">=3.9"}],
            "2.0": [{"requires_python": ">=3.10,<3.15"}],
            "3.0": [{"requires_python": ">=3.11"}],
            "4.0": [{"requires_python": ">=3.10,<3.14"}],
            "5.0": [{"requires_python": ">=3.10", "yanked": True}],
            "6.0rc1": [{"requires_python": ">=3.10"}],
            "7.0.dev1": [{"requires_python": ">=3.10"}],
            "8.0": [],
        }
        self.assertEqual(
            pins.latest_compatible(releases, ["3.10", "3.13", "3.14"]), "2.0"
        )

    def test_numeric_version_order_and_available_non_yanked_file(self):
        releases = {
            "2.9": [{}],
            "2.10": [{"yanked": True}, {"requires_python": ">=3.10"}],
        }
        self.assertEqual(pins.latest_compatible(releases, ["3.10"]), "2.10")

    def test_no_common_release_fails(self):
        with self.assertRaisesRegex(RuntimeError, "every target Python"):
            pins.latest_compatible({"2.0": [{"requires_python": ">=3.11"}]}, ["3.10"])

    def test_updates_runtime_and_build_pins_without_changing_package_version(self):
        text = (
            '[build-system]\nrequires = ["setuptools==80.9.0"]\n'
            '[project]\nname = "homelab-secrets"\nversion = "0.1.0"\n'
            'dependencies = ["example[extra]==1.0"]\n'
        )
        result = tomllib.loads(
            pins.refresh(text, ["3.10", "3.14"], lambda _: {"2.0": [{}]})
        )
        self.assertEqual(result["project"]["version"], "0.1.0")
        self.assertEqual(result["project"]["dependencies"], ["example[extra]==2.0"])
        self.assertEqual(result["build-system"]["requires"], ["setuptools==2.0"])
