"""Regression checks for choosing an offline bundle across Python versions."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'offline_packaging', Path(__file__).resolve().parents[1] / 'scripts/offline.py')
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)


class BundleSelectionTests(unittest.TestCase):
    def test_selects_native_dependencies_for_each_python_minor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for minor in ('3.12', '3.13'):
                info = dict(platform='linux-x86_64', implementation='cpython', python=minor)
                bundle = root / offline.bundle_key(info)
                bundle.mkdir()
                (bundle / 'target.json').write_text(json.dumps(info))
            for minor in ('3.12', '3.13'):
                info = dict(platform='linux-x86_64', implementation='cpython', python=minor)
                with self.subTest(python=minor), patch.object(offline, 'BUNDLES', root), \
                        patch.object(offline, 'target', return_value=info):
                    self.assertEqual(offline.select_bundle(), root / offline.bundle_key(info))

    def test_other_minor_can_try_available_compatible_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = dict(platform='linux-x86_64', implementation='cpython', python='3.13')
            bundle = root / offline.bundle_key(info)
            bundle.mkdir()
            (bundle / 'target.json').write_text(json.dumps(info))
            with patch.object(offline, 'BUNDLES', root), patch.object(
                    offline, 'target', return_value={**info, 'python': '3.14'}):
                self.assertEqual(offline.select_bundle(), bundle)

    def test_never_chooses_another_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = dict(platform='linux-x86_64', implementation='cpython', python='3.13')
            bundle = root / offline.bundle_key(info)
            bundle.mkdir()
            (bundle / 'target.json').write_text(json.dumps(info))
            with patch.object(offline, 'BUNDLES', root), patch.object(
                    offline, 'target', return_value={**info, 'platform': 'linux-aarch64'}):
                with self.assertRaisesRegex(RuntimeError, 'No bundle'):
                    offline.select_bundle()
