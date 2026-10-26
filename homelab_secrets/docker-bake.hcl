group "default" {
  targets = ["test", "upgrade-tests", "container-test"]
}

group "ci" {
  targets = ["test", "upgrade-tests", "container-test"]
}

variable "DISTRIBUTIONS" {
  default = [
    { name = "ubuntu-22-04", image = "ubuntu:22.04", python = "3.10" },
    { name = "ubuntu-26-04", image = "ubuntu:26.04", python = "3.14" },
    { name = "debian-trixie", image = "debian:trixie", python = "3.13" },
  ]
}

function "platform_args" {
  params = [distro]
  result = {
    BASE_IMAGE = distro.image
    EXPECTED_PYTHON = distro.python
    DISTRO = distro.name
  }
}

target "_common" {
  context = "."
  dockerfile = "ci/Dockerfile"
  platforms = ["linux/amd64"]
}

target "test" {
  inherits = ["_common"]
  name = "test-${distro.name}"
  matrix = { distro = DISTRIBUTIONS }
  args = platform_args(distro)
  target = "test"
  # Reuse OS preparation, but always execute the installation and tests.
  no-cache-filter = ["test"]
  output = ["type=cacheonly"]
}

# The resolver uses the Python 3.14 row for stdlib TOML support.
target "_resolver" {
  inherits = ["_common"]
  args = merge(
    platform_args([for distro in DISTRIBUTIONS : distro if distro.python == "3.14"][0]),
    { SUPPORTED_PYTHONS = jsonencode([for distro in DISTRIBUTIONS : distro.python]) }
  )
}

target "refresh-pins" {
  inherits = ["_resolver"]
  target = "pins-export"
  no-cache-filter = ["refresh-pins"]
  output = ["type=local,dest=."]
}

target "upgrade-tests" {
  inherits = ["_resolver"]
  target = "upgrade-tests"
  no-cache-filter = ["upgrade-tests"]
  output = ["type=cacheonly"]
}

target "upgrade" {
  inherits = ["_common"]
  name = "upgrade-${distro.name}"
  matrix = { distro = DISTRIBUTIONS }
  args = platform_args(distro)
  target = "bundle-export"
  no-cache-filter = ["upgrade"]
  output = ["type=local,dest=."]
}

variable "IMAGE_TAG" {
  default = null
}

target "container-image" {
  context = "."
  dockerfile = "ci/Containerfile"
  platforms = ["linux/amd64"]
  target = "runtime"
  tags = IMAGE_TAG == null ? [] : [IMAGE_TAG]
  output = ["type=docker"]
}

target "container-test" {
  context = "."
  dockerfile = "ci/Containerfile"
  platforms = ["linux/amd64"]
  target = "image-test"
  no-cache-filter = ["image-test"]
  output = ["type=cacheonly"]
}
