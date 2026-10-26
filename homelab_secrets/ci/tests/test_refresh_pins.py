import sys
import unittest
from pathlib import Path

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import refresh_pins as pins


class RefreshPinsTests(unittest.TestCase):
    def test_release_response_validation(self) -> None:
        valid: dict[str, object] = {"releases": {"1.0": [{}]}}
        self.assertEqual(
            pins.parse_releases(valid),
            {"1.0": [{"requires_python": None, "yanked": False}]},
        )
        cases: tuple[object, ...] = (
            None,
            {},
            {"releases": []},
            {"releases": {"1.0": {}}},
            {"releases": {"1.0": [None]}},
            {"releases": {"1.0": [{"requires_python": 3}]}},
            {"releases": {"1.0": [{"yanked": "false"}]}},
        )
        for malformed in cases:
            with self.subTest(value=malformed), self.assertRaises(ValueError):
                pins.parse_releases(malformed)

    def test_latest_release_must_support_every_python_and_not_be_yanked(self) -> None:
        releases: pins.Releases = {
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

    def test_numeric_version_order_and_available_non_yanked_file(self) -> None:
        releases: pins.Releases = {
            "2.9": [{}],
            "2.10": [{"yanked": True}, {"requires_python": ">=3.10"}],
        }
        self.assertEqual(pins.latest_compatible(releases, ["3.10"]), "2.10")

    def test_no_common_release_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "every target Python"):
            pins.latest_compatible({"2.0": [{"requires_python": ">=3.11"}]}, ["3.10"])

    def test_updates_runtime_and_build_pins_without_changing_package_version(
        self,
    ) -> None:
        text = (
            '[build-system]\nrequires = ["setuptools==80.9.0"]\n'
            '[project]\nname = "homelab-secrets"\nversion = "0.1.0"\n'
            'dependencies = ["example[extra]==1.0"]\n'
        )
        result = tomllib.loads(
            pins.refresh(
                text, ["3.10", "3.14"], lambda _: {"2.0": [pins.ReleaseFile()]}
            )
        )
        self.assertEqual(result["project"]["version"], "0.1.0")
        self.assertEqual(result["project"]["dependencies"], ["example[extra]==2.0"])
        self.assertEqual(result["build-system"]["requires"], ["setuptools==2.0"])
