group "default" {
  targets = ["test"]
}

group "ci" {
  targets = ["test"]
}

target "test" {
  name = "test-${distro.name}"
  matrix = {
    distro = [
      { name = "ubuntu-22-04", image = "ubuntu:22.04", python = "3.10" },
      { name = "ubuntu-26-04", image = "ubuntu:26.04", python = "3.14" },
      { name = "debian-trixie", image = "debian:trixie", python = "3.13" },
    ]
  }
  context = "."
  dockerfile = "ci/Dockerfile"
  target = "test"
  platforms = ["linux/amd64"]
  args = {
    BASE_IMAGE = distro.image
    EXPECTED_PYTHON = distro.python
    DISTRO = distro.name
  }
  # Reuse OS preparation, but always execute the installation and tests.
  no-cache-filter = ["test"]
  output = ["type=cacheonly"]
}
