# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS prerequisites
ARG DISTRO
ENV DEBIAN_FRONTEND=noninteractive
# The base images normally delete apt's downloaded packages after installation.
RUN rm -f /etc/apt/apt.conf.d/docker-clean
RUN --mount=type=cache,id=apt-packages-${DISTRO},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-${DISTRO},target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends make python3 python3-venv
WORKDIR /project

FROM prerequisites AS test
ARG EXPECTED_PYTHON
COPY --link Makefile pyproject.toml ./
COPY --link src/ ./src/
COPY --link scripts/ ./scripts/
COPY --link tests/ ./tests/
COPY --link ci/assert-runtime.py ./ci/assert-runtime.py
COPY --link offline/cpython-${EXPECTED_PYTHON}-linux-x86_64/ ./offline/cpython-${EXPECTED_PYTHON}-linux-x86_64/
RUN --network=none python3 ci/assert-runtime.py "${EXPECTED_PYTHON}" && make test
