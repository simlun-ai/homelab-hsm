PYTHON ?= python3
VENV ?= $(CURDIR)/.venv
.DEFAULT_GOAL := help

.PHONY: help build build-upgrade install test ci lint typecheck format container-image container-image-scan clean
help:
	@echo 'make build    Rebuild our wheel with locked dependencies (online backend setup)'
	@echo 'make build-upgrade  Refresh dependency pins and all bundles, then run make ci'
	@echo 'make install  Install the bundle into .venv (offline)'
	@echo 'make container-image  Build and load the local slim Trixie image'
	@echo 'make container-image-scan  Scan the runtime image with containerized Grype'
	@echo 'make typecheck  Check all Python with pinned Pyright in Docker'
	@echo 'make lint     Check all Python with pinned Ruff in Docker'
	@echo 'make format   Apply safe Ruff fixes and formatting in Docker'
	@echo 'make ci       Run all supported distributions in parallel with Buildx Bake'
	@echo 'make test     Install offline and run tests'
	@echo 'make clean    Remove temporary build output; preserve .venv and offline/'

build:
	$(PYTHON) scripts/offline.py build

build-upgrade:
	$(PYTHON) scripts/upgrade.py
	$(MAKE) ci

install:
	$(PYTHON) -B scripts/offline.py install --venv "$(VENV)"

test: install

ci:
	@echo 'SECURITY SCAN: report-only; green CI does not mean zero vulnerabilities. Scanner errors still fail CI.'
	docker buildx bake --file docker-bake.hcl --progress=plain ci
	$(MAKE) container-image
	$(PYTHON) ci/test_container_run.py

container-image:
	$(PYTHON) scripts/container_image.py

container-image-scan:
	docker buildx bake --file docker-bake.hcl --progress=plain container-image-scan

clean:
	rm -rf build dist .build src/*.egg-info

lint:
	docker buildx bake --file docker-bake.hcl --progress=plain lint

format:
	docker buildx bake --file docker-bake.hcl --progress=plain lint-tool
	docker run --rm --network none --user "$$(id -u):$$(id -g)" \
	  --mount "type=bind,src=$(CURDIR),dst=/project" \
	  homelab-secrets-ruff:local sh -c \
	  'ruff check --fix --no-cache src scripts tests ci && ruff format --no-cache src scripts tests ci'

typecheck:
	docker buildx bake --file docker-bake.hcl --progress=plain typecheck
