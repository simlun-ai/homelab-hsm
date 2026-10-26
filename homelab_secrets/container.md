# Container CLI

From `homelab_secrets/`, run:

```sh
make container-image
```

This builds and loads a local `linux/amd64` image based on `debian:trixie-slim`.
Its name/tag come from the source-validated project wheel (currently
`homelab-secrets:0.1.0`), whose metadata is built from `pyproject.toml`.
Rebuild stale project wheels before building the image. No image is published.
Docker/Buildx/BuildKit is required; an ARM host needs amd64 emulation configured.
Base images and Debian Python packages may need internet. Python packages install
from the committed Python 3.13 wheelhouse with networking disabled and hash
verification, into system Python—not a virtualenv. The runtime image contains
neither pip nor the wheelhouse, test suite, or native build tools.

The image runs as UID/GID `65532:65532` by default. These need no USB device:

```sh
docker run --rm -it homelab-secrets:0.1.0 wrap --help
docker run --rm -it homelab-secrets:0.1.0 unwrap --help
```

## Scan the local image

Install [Grype](https://oss.anchore.com/docs/installation/grype/) on the host
and ensure `grype` is on `PATH`, then run from `homelab_secrets/`:

```sh
make container-image-scan
```

This builds and loads the image using the same validated name/tag as
`make container-image`, then scans that image explicitly from the local Docker
daemon with `grype docker:<name>:<version> --output table`. The vulnerability
report appears directly in the terminal. Grype may need internet to download or
refresh its vulnerability database. Findings are informational: no severity
threshold is set, while build and scanner errors fail the target. This is an
opt-in local command, separate from `make ci`.

## Try the public fake key

Both commands support `--fake-yubikey`. It defaults `--root-key` to
`golden-fake-1`; an explicitly different root ID is rejected. The reserved ID
also fails without `--fake-yubikey`. Input records never enable fake mode.

The fake responder calculates HMAC-SHA1 with the hard-coded, PUBLIC 20-byte key
`000102030405060708090a0b0c0d0e0f10111213`. It skips USB/touch checks and uses the
normal HKDF/AES-GCM record format and verification. Anyone can decrypt these
records; use disposable test data only. A notice is written to stderr.

A complete volume-free round trip (Bash). Type `public-demo-password` at the
hidden prompt; your random salt, nonce, and ciphertext will differ.

```console
$ read -s -p "Demo password (hidden): " demo_password
$ printf '%s' "$demo_password" |
    docker run --rm -i homelab-secrets:0.1.0 wrap \
      --fake-yubikey --stdin --stdout \
      --key-id homelab/v1/test/credential/demo/r1 > credential-demo.json
$ cat credential-demo.json | python3 -m json.tool
{
    "ciphertext": "0fEdZ/WskhtjwEmd5TC0CmFZrWSCAbP0TSNQhPybH2Vz1sIz",
    "format": "homelab-wrap-v1",
    "key_id": "homelab/v1/test/credential/demo/r1",
    "nonce": "yyMADoKWj0gbyK+k",
    "revision": 1,
    "root_key": "golden-fake-1",
    "salt": "/jSJ2UaJMb6QKOd489cooBpJZ5p+xd1M2h4bJwL4Oj0="
}
$ cat credential-demo.json |
    docker run --rm -i homelab-secrets:0.1.0 unwrap \
      --fake-yubikey --stdin --stdout \
      --key-id homelab/v1/test/credential/demo/r1
public-demo-password
```

Use `-i`, **without `-t`**, for binary pipelines. TTY allocation can transform
bytes and combine stdout/stderr. Status and touch prompts use stderr; stdout
contains only verified ciphertext or authenticated plaintext. Unwrapped bytes
have no extra newline. Route real plaintext directly to a trusted consumer.

## Pass through a real YubiKey on Linux

Configure host OTP access using the parent repository's step-00 setup/udev
instructions. Identify the YubiKey's **OTP hidraw node**, rather than its FIDO
interface. If the host project environment is installed, this prints accessible
OTP nodes without issuing a challenge:

```sh
.venv/bin/python -c 'from ykman.hid import list_otp_devices; print("\n".join(str(d.fingerprint) for d in list_otp_devices()))'
```

Inspect the node and its host udev permissions. The selected node must allow
read/write by your user or the device's group. The following examples use a
normal Docker daemon, a non-root host user, and a non-root container process.
Set `YUBIKEY_HIDRAW` to the actual OTP node; `/dev/hidraw3` is only an example.

```sh
YUBIKEY_HIDRAW=/dev/hidraw3
stat -c '%A %u:%g %n' "$YUBIKEY_HIDRAW"

# Bash array: pass only this device and its numeric device group.
device=(
  --device="$YUBIKEY_HIDRAW:$YUBIKEY_HIDRAW:rw"
  --user="$(id -u):$(id -g)"
  --group-add="$(stat -c '%g' "$YUBIKEY_HIDRAW")"
)
```

Group access must actually grant read/write in the node's mode; host desktop
ACLs alone may not be reproduced on Docker's device node. Use the host's udev
group configuration when needed. There is no need for `--privileged`, a PC/SC
service, or mounting all of `/dev` or `/dev/bus/usb`. Recheck the node after
unplugging/reinserting the key and start a new container.

The commands `trusted-secret-producer` and `trusted-secret-consumer` below are
placeholders for your trusted programs. They must keep plaintext out of files
and logs. Choose the real credential/root IDs independently of the record.

```sh
set -o pipefail
set -o noclobber  # Do not overwrite an existing ciphertext record on the host.

trusted-secret-producer |
  docker run --rm -i "${device[@]}" homelab-secrets:0.1.0 wrap \
    --stdin --stdout --root-key golden-1 \
    --key-id homelab/v1/example/credential/demo/r1 > credential.json

cat credential.json |
  docker run --rm -i "${device[@]}" homelab-secrets:0.1.0 unwrap \
    --stdin --stdout --root-key golden-1 \
    --key-id homelab/v1/example/credential/demo/r1 |
  trusted-secret-consumer
```

Run real-credential examples from a private records directory, outside this code
repository. Only ciphertext is persisted. No volumes are mounted. Follow stderr touch
prompts: leave the token untouched for the initial gate probe, then touch when
requested. The CLI verifies wrapping before emitting ciphertext, but streaming
output cannot make host redirection atomic; a failed/interrupted command may
leave an empty or incomplete ciphertext file. Check exit status with pipefail.
The container cannot inspect the host's downstream redirections: do not redirect
unwrapped stdout into plaintext files or capture it in logs.

### Fully rootless Docker

A non-root container process and a rootless daemon are different configurations.
Rootless Docker uses user namespaces: container root maps to the daemon's host
user, while other container UIDs/GIDs map into subordinate ID ranges. Therefore
host UID/GID and group flags above must not be copied unchanged into a rootless
setup. Access depends on host permissions and the runtime's device support;
verify those mappings and device access on that host first. The normal-daemon
non-root recipe is the documented baseline. Actual YubiKey passthrough and fully
rootless hardware access remain unverified by automated tests.

## Automated checks

`make ci` tests all supported distributions and the slim runtime image, then
loads the tagged image and checks real `docker run` help, non-root execution,
and a binary fake-key round trip. Image tests also cover empty/binary payloads,
tampering, wrong context/root IDs, size limits, and stderr/stdout separation.
They run without USB devices or volumes and without network access during
installation/secret operations. Fake-key tests do not establish hardware access.
