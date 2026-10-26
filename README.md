# Homelab HSM

Python library and CLI for YubiKey-backed wrapping of homelab credentials.
The [homelab_secrets/](homelab_secrets/README.md) project owns record cryptography,
read-only slot 2 access, `homelab-wrap`/`homelab-unwrap`, tests, dependency pins,
committed offline wheel bundles, and a local container image.

This repository contains code and public disposable test fixtures, not stored
credential records. The Python distribution remains `homelab-secrets`, with
imports under `homelab_secrets`. The YubiKey performs the hardware-backed HMAC
operation; `--fake-yubikey` uses a public software key for tests only.

In [homelab](https://github.com/simlun-ai/homelab), this code is pinned at
`tools/homelab-hsm`. Wrapped records live independently in the private
`homelab-secrets` repository at `secrets/wrapped`; the public manifest remains
`secrets/manifest.json`. Code installation and automated tests do not need the
private records checkout. See the parent's
[storage and recovery instructions](https://github.com/simlun-ai/homelab/blob/main/docs/security/encrypted-record-storage.md).

For standalone offline installation, run `make -C homelab_secrets install`, then
`source homelab_secrets/.venv/bin/activate`. See the project README for system
prerequisites, supported platforms, build/test commands, and library usage.

Never commit credential records, plaintext secrets, password hashes, private
keys, HMAC responses, or golden-key material here. Tests use clearly public
disposable keys and dummy payloads only. Recovery kits retain full clones of
the parent, this code repository, and the private records repository.
