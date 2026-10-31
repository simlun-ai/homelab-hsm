# Root-key generation and YubiKey setup

`homelab-hsm` owns generation, OTP programming and verification. It does not
store keys or know password-manager paths, token inventories or workspaces.
Install the offline bundle first; see [README.md](README.md).

| Command | Input / output |
| --- | --- |
| `homelab-hsm generate-key` | Generate 20 random bytes; emit 40 lowercase hex characters and a newline to a pipe/socket |
| `homelab-hsm inspect` | Show public firmware, serial if available, and slot occupancy |
| `homelab-hsm program --label primary` | Read key from a pipe; confirm physical label; program and verify slot 2 |
| `homelab-hsm program --label primary --replace` | Explicitly allow replacing occupied slot 2 after an erase confirmation |
| `homelab-hsm verify --label primary` | Read key from a pipe; confirm label; compare hardware HMAC with software |
| `homelab-hsm verify-set --labels primary spare` | Read key once; verify distinct tokens and shared in-memory wrap/unwrap |

Use at least two distinct labels for set verification. Labels are public,
1–64 characters, starting with an ASCII letter/digit and containing only those
characters plus dot, underscore and hyphen. They identify physical labels,
not a key generation. The dummy verification context is not a production record.

Secret input is exactly 40 ASCII hexadecimal characters with an optional final
newline. Leading zeros are preserved. Empty input, extra lines, whitespace and
oversized input fail before opening a token. Output from a trusted secret store
can feed stdin directly; enable shell `pipefail` and stop on any pipeline failure.
Do not put secrets in arguments, environment variables, command substitutions,
files, clipboard, logs or `tee`. Direct terminal/file secret streams are rejected;
indirect capture cannot be detected. A shell may create a redirected file before
the CLI rejects it. The generator is a low-level producer: it cannot detect an
existing stored generation. The storage workflow must prevent replacement.

Confirmations read `/dev/tty`, never stdin. Programming and verification require
a controlling terminal; touch instructions and diagnostics use stderr. Run as
the local user with OTP HID permissions, without sudo. Use a local unrecorded
terminal in a trusted offline environment. Hardening disables core dumps and SDK
logging; Python cannot guarantee memory zeroization or control OS swap/suspend.

Connect exactly one token. Inspection precedes programming. Slot 2 uses
HMAC-SHA1, fixed-length 64-byte challenges, required touch and disabled updates.
Slot 1 is preserved. The program confirmation is `program primary slot2`;
occupied-slot replacement requires
`replace primary slot2 and erase existing credential`. Do not blindly retry a
failed write: reinsert and verify with the saved key. Never generate another key
to resolve a verification failure. Existing programming access codes require
separate handling.

Verification tests three public challenges, checking refusal without touch before
each response. Set verification rejects repeated serials when available and
requires removal between tokens. Where serials are unavailable, physical labels
remain the operator's responsibility. All tokens and software must unwrap the
same disposable in-memory record. Only public PASS results are printed; no
responses or derived keys are emitted. Hardware compatibility, including older
Standard models, must be verified on the actual devices.

The [level1vault runbook](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md)
owns encrypted `pass` custody and pipes for its live OS.
The [homelab runbook](https://github.com/simlun-ai/homelab/blob/main/docs/installation/00-yubikey-setup.md)
owns that deployment's four-token inventory and acceptance results.
