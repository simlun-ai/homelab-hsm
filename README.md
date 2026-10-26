# Homelab wrapped secrets

Private ciphertext store mounted at `secrets/wrapped` in `simlun-ai/homelab`.
Keep this repository private. Wrapped credentials are authenticated
`homelab-wrap-v1` records. The [homelab_secrets/](homelab_secrets/README.md)
Python project owns the library, `homelab-wrap`/`homelab-unwrap`, and their tests
and dependency pins. Commit source and ciphertext, never plaintext secrets,
password hashes, private keys, HMAC responses, or golden-key material. Tests
must use clearly public disposable keys and dummy payloads only.

The project also commits its prebuilt wheel and complete Python dependency bundle.
Run `make -C homelab_secrets install` to install offline, then activate with
`source homelab_secrets/.venv/bin/activate`. See the project README for system
prerequisites, supported platform, and build/test commands.

The public manifest lives in the parent repository at `secrets/manifest.json`.
Follow its `docs/security/encrypted-record-storage.md` for updates and recovery.
Push changes here before committing the updated submodule pointer there.
Recovery USBs must retain complete clones of both repositories.

No production credential records have been generated yet.


