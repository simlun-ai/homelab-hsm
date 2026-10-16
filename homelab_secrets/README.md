# homelab-secrets

Importable `homelab_secrets` library and two commands: `homelab-wrap` and
`homelab-unwrap`. Uses the existing `homelab-wrap-v1` format without changing
record paths or requiring the parent repository/manifest. Linux, Python 3.11–3.14.

## Install

From this directory, while online and before handling secrets:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --editable .
.venv/bin/python -m pip check
.venv/bin/python -I -B -m unittest discover -s tests -v
```

The project `pyproject.toml` owns crypto/token dependency pins. System USB libraries
and local-user OTP access must already be configured; the parent step-00 installer
does this. No `sudo` for token operations. In the parent checkout, use
`make -C support/yubikey tools` and `make -C support/yubikey test` instead; commands
are then in `support/yubikey/.venv/bin/`.

Install locally, not from a package index. The parent submodule pin selects code
and records together. Rerun installation after changing the checkout. Recovery
clones include source, not a portable virtualenv or an offline dependency bundle;
prepare dependencies before going offline. Offline packaging remains pending.

## CLI

Connect exactly one configured, verified YubiKey. Slot **2** is fixed; slot 1 is
never written. Commands never program tokens. Follow the stderr prompts: first
do not touch for the touch-gate probe, then touch for each HMAC operation.

Illustrative context below; choose the real identifier/root independently of
the record. In the parent, use its public manifest and credential catalogue.
Never rename an identifier just because its file moved.

```sh
.venv/bin/homelab-wrap \
  --key-id homelab/v1/example/credential/demo/r1 --root-key golden-1 \
  --output ../example.json

.venv/bin/homelab-unwrap \
  --key-id homelab/v1/example/credential/demo/r1 --root-key golden-1 \
  --input ../example.json --reveal
```

Wrap prompts twice for UTF-8 text without an appended newline. For exact binary
bytes, pipe a trusted in-memory producer into `homelab-wrap --stdin ...`.
Wrap verifies by unwrapping before exclusive ciphertext creation; existing files
are never overwritten. `--revision` defaults to 1. This is not a rotation or
rollback-protection workflow.

Unwrap requires either `--reveal` (explicit confirmation, escaped Python bytes
literal on a local unrecorded terminal) or `--stdout` (exact bytes, no added
newline, to a trusted consumer's stdin). The consumer must also keep plaintext
off disk and out of logs. Prompt/status messages use stderr. Plaintext streams
must be pipes/sockets; direct regular-file redirection and `/dev/null` are
rejected. A shell can still create/truncate a redirected file before the CLI
rejects it. Indirect capture such as `tee` cannot be detected: do not use it.

Do not put plaintext in arguments, environment variables, temporary files,
clipboard, logs, or Git. Persist ciphertext only in this private repository or
approved encrypted storage. Review your target path; the standalone CLI does
not know the parent repository boundary. Errors suppress potentially secret
exception details. An interrupted write may leave an incomplete ciphertext file;
inspect it before retrying, never overwrite an established credential blindly.

## Library

```python
from homelab_secrets import wrap, unwrap
from homelab_secrets.runtime import harden
from homelab_secrets.yubikey import token, respond, require_no_response_without_touch

harden()  # Explicit opt-in before handling secrets; Linux, core dumps disabled.
with token() as session:
    require_no_response_without_touch(session)
    callback = lambda challenge: respond(session, challenge)
    record = wrap(plaintext, key_id, root_key, 1, callback)
    recovered = unwrap(record, key_id, root_key, callback)
```

`plaintext`, `record`, and returned plaintext are bytes. The callback receives a
64-byte challenge and returns a 20-byte HMAC-SHA1 response. `wrap` returns JSON
bytes but does not persist or verify them; callers must verify before writing,
as the CLI does. `unwrap` validates size/schema/context before calling the
responder and releases plaintext only after authenticated decryption.

Imports do not open USB devices, harden the process, or print. The core library
does not need the token SDK imported; tests can inject a responder using clearly
public dummy keys. Explicit software recovery can inject the same protocol from
the separately held Level 1 golden key; there is no CLI software-recovery mode
or golden-key input option in this release.

Application callers own process hardening, expected context, consumer delivery,
sanitized errors, and memory lifetimes. Python object deletion cannot guarantee
zeroization; this code does not change OS swap/suspend policy. Physical-token
compatibility and recovery drills remain pending; automated tests use no hardware.
