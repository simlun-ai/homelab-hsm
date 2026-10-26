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

    def test_rebuild_reuses_locked_dependencies_and_rejects_modified_wheels(self):
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, output = root / 'bundle', root / 'output'
            (bundle / 'wheels').mkdir(parents=True)
            output.mkdir()
            wheel = bundle / 'wheels/example-1.0-py3-none-any.whl'
            with zipfile.ZipFile(wheel, 'w') as archive:
                archive.writestr('example-1.0.dist-info/METADATA', 'Name: example\nVersion: 1.0\n')
            original = wheel.read_bytes()
            (bundle / 'requirements.lock').write_text(
                'example==1.0 --hash=sha256:' + hashlib.sha256(original).hexdigest() + '\n')
            offline.copy_locked_dependencies(bundle, output)
            self.assertEqual((output / wheel.name).read_bytes(), original)
            wheel.write_bytes(original + b'modified')
            with self.assertRaisesRegex(RuntimeError, 'modified locked wheel'):
                offline.copy_locked_dependencies(bundle, output)
