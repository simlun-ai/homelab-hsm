"""Get the image tag from the source-validated Trixie project wheel."""
import email
import hashlib
import json
from pathlib import Path
import re
import zipfile

import offline


def image_metadata():
    bundle = offline.BUNDLES / 'cpython-3.13-linux-x86_64'
    info = json.loads((bundle / 'target.json').read_text())
    if info['source_sha256'] != offline.source_digest():
        raise RuntimeError('Rebuild the committed project wheels before building the image')
    wheel, = (bundle / 'wheels').glob('homelab_secrets-*.whl')
    with zipfile.ZipFile(wheel) as archive:
        path, = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        metadata = email.message_from_bytes(archive.read(path))
    name, version = metadata['Name'], metadata['Version']
    expected = f'{name}=={version} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}'
    if expected not in (bundle / 'requirements.lock').read_text().splitlines():
        raise RuntimeError('The project wheel does not match its lock')
    tag = f'{name}:{version}'
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', tag):
        raise RuntimeError('Project name/version cannot be used as a Docker image tag')
    return {'name': name, 'version': version, 'tag': tag}


if __name__ == '__main__':
    print(json.dumps(image_metadata()))
