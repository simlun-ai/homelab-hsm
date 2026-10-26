PYTHON ?= python3
.DEFAULT_GOAL := help

.PHONY: help build install test ci clean
help:
	@echo 'make build    Build and replace the committed offline bundle (online)'
	@echo 'make install  Install the bundle into .venv (offline)'
	@echo 'make ci       Run all supported distributions in parallel with Buildx Bake'
	@echo 'make test     Install offline and run tests'
	@echo 'make clean    Remove temporary build output; preserve .venv and offline/'

build:
	$(PYTHON) scripts/offline.py build

install:
	$(PYTHON) scripts/offline.py install

test: install

ci:
	docker buildx bake --file docker-bake.hcl --progress=plain ci

clean:
	rm -rf build dist .build src/*.egg-info
