# homelab-secrets

Importable `homelab_secrets` library and two commands: `homelab-wrap` and
`homelab-unwrap`. Uses the existing `homelab-wrap-v1` format without changing
record paths or requiring the parent repository/manifest. Linux, Python 3.10–3.14.

## Install

From this directory, using the committed bundle (no internet required):

```sh
make install
source .venv/bin/activate
homelab-wrap --help
homelab-unwrap --help
```

Prerequisites: GNU Make, Python with `venv`/`ensurepip`, and configured
local-user OTP access. Install these
before going offline; the parent step-00 installer configures USB access. No
`sudo` for token operations. Activation is optional: scripts can invoke
`.venv/bin/homelab-wrap` and `.venv/bin/homelab-unwrap` directly.

Committed bundles support **Linux x86_64** on:

| Distribution | Default Python |
| --- | --- |
| Ubuntu 22.04 LTS | CPython 3.10 |
| Ubuntu 26.04 LTS | CPython 3.14 |
| Debian 13 Trixie | CPython 3.13 |

The installer selects `offline/cpython-<minor>-linux-x86_64/`; each bundle has
its own wheels, `requirements.lock`, and `target.json`. A different supported
Python minor version is attempted with a warning using an available bundle.
Installation succeeds only if the wheels are compatible and all tests pass.
Different architectures and libc versions below the bundle’s recorded minimum
are rejected. Builds inspect native wheels with `readelf` to determine that
minimum, rather than requiring the build machine’s glibc version.

On these distributions, prepare the system before going offline:

```sh
sudo apt install make python3-venv
```

Local-user OTP access must also be configured as described above. `make install`
uses the distribution’s default Python. When switching an existing checkout
between Python minor versions, remove `.venv/` first.

A virtualenv is local to the machine; recovery clones retain `offline/` instead.

`make install` creates `.venv/` and installs only local wheels with exact versions
and SHA-256 verification. Repeat it after changing the checkout or rebuilding:
it force-reinstalls even when the package version is unchanged. No dependency
resolution against an index or compilation happens during installation.

### Build and test

```sh
make build    # Online: build our wheel and every transitive dependency wheel
make test     # Offline: install the bundle and run the tests
make clean    # Remove temporary build output; preserve .venv/ and offline/
```

On Ubuntu or Debian, building additionally requires `build-essential`, `python3-dev`,
`binutils`, `libpcsclite-dev`, and `swig` (not needed for offline installation). The PC/SC
headers build the SDK’s `pyscard` dependency. Our OTP/HMAC path uses Linux HID
directly and requires neither `libpcsclite1` nor the `pcscd` service at runtime.
Use `make PYTHON=python3.14 build` to select the build interpreter.
`pyproject.toml` owns the package version and direct dependency pins. Transitive
versions are resolved during each build and recorded with hashes in
the selected bundle’s `requirements.lock`. Builds run in an isolated environment and verify a
fresh installation and the test suite before replacing the previous bundle.
Failed builds retain the existing bundle. Installation checks a source and
`pyproject.toml` fingerprint, so same-version source edits require rebuilding
each supported bundle before committing.

Commit all of `offline/` alongside source changes. Each successful build replaces
only the running interpreter’s bundle, preserving the other targets; rebuilding the same version is
expected. No tags or version bumps are required. Git history retains old bundles.
Wheels are ordinary Git files, with no LFS or external download needed to install.
The parent submodule pin selects code, bundle, and records together. Existing
parent `support/yubikey` Make targets manage their own environment separately.

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

