"""Build and load the local image tagged from validated project metadata."""
import os
import subprocess

from image_metadata import image_metadata
from offline import ROOT

if __name__ == '__main__':
    info = image_metadata()
    subprocess.run(['docker', 'buildx', 'bake', '--file', 'docker-bake.hcl',
                    '--progress=plain', 'container-image'], cwd=ROOT, check=True,
                   env={**os.environ, 'IMAGE_TAG': info['tag']})
    print(f"Built local image {info['tag']}")
