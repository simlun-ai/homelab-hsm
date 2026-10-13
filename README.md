# Homelab wrapped secrets

Private ciphertext store mounted at `secrets/wrapped` in `simlun-ai/homelab`.
Keep this repository private. Commit only authenticated `homelab-wrap-v1`
records, never plaintext secrets, password hashes, private keys, HMAC responses,
or golden-key material.

The public manifest lives in the parent repository at `secrets/manifest.json`.
Follow its `docs/security/encrypted-record-storage.md` for updates and recovery.
Push changes here before committing the updated submodule pointer there.
Recovery USBs must retain complete clones of both repositories.

No production credential records have been generated yet.
