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
            for minor in ('3.10', '3.13', '3.14'):
                info = dict(platform='linux-x86_64', implementation='cpython', python=minor)
                bundle = root / offline.bundle_key(info)
                bundle.mkdir()
                (bundle / 'target.json').write_text(json.dumps(info))
            for minor in ('3.10', '3.13', '3.14'):
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
                    offline, 'target', return_value={**info, 'python': '3.11'}):
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

    def test_source_change_requires_rebuild_even_with_same_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
            source = root / 'src/example.py'
            source.parent.mkdir()
            source.write_text('value = 1\n')
            with patch.object(offline, 'ROOT', root):
                recorded = {**offline.target(), 'source_sha256': offline.source_digest()}
                (root / 'target.json').write_text(json.dumps(recorded))
                source.write_text('this is invalid python !!!\n')
                with patch.object(offline, 'select_bundle', return_value=root), \
                        patch.object(offline, 'install_wheels') as install:
                    with self.assertRaisesRegex(RuntimeError, 'does not match the source'):
                        offline.install()
                    install.assert_not_called()
                    self.assertFalse((root / '.venv').exists())
