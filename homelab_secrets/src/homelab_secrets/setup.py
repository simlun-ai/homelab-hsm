"""Generate a root key and provision or verify OTP HMAC-SHA1 tokens."""

import argparse
import hmac
import re
import secrets
import sys
from collections.abc import Sequence
from functools import partial

from ykman.hid import list_otp_devices
from yubikit.yubiotp import SLOT, HmacSha1SlotConfiguration, YubiOtpSession

from homelab_secrets import wrapping
from homelab_secrets.cli import require_pipe
from homelab_secrets.runtime import harden
from homelab_secrets.yubikey import require_no_response_without_touch, respond, token

TEST_ID = "homelab/v1/setup/verification/cross-token/r1"
TEST_ROOT = "setup-verification"
CHALLENGES = (b"A" * 64, bytes(range(64)), wrapping.challenge(TEST_ID))


def require_terminal() -> None:
    with open("/dev/tty", encoding="utf-8") as terminal:
        if not terminal.isatty():
            raise RuntimeError("Token setup requires a controlling terminal")


def prompt(message: str) -> str:
    # Confirmation never consumes the secret pipe, even when stdin is exhausted.
    with open("/dev/tty", "w", encoding="utf-8") as output:
        output.write(message)
        output.flush()
    with open("/dev/tty", encoding="utf-8") as terminal:
        answer = terminal.readline(256)
    if not answer.endswith("\n"):
        raise RuntimeError("Missing or oversized terminal confirmation")
    return answer[:-1]


def generate_key() -> None:
    require_pipe(sys.stdout)
    sys.stdout.write(secrets.token_hex(20) + "\n")
    sys.stdout.flush()


def read_golden_key() -> bytes:
    require_pipe(sys.stdin)
    # Read through EOF, with a bound: never silently accept metadata or trailing data.
    value = sys.stdin.buffer.read(42)
    if not re.fullmatch(rb"[0-9a-fA-F]{40}\n?", value):
        raise ValueError("Expected one 40-character hexadecimal key")
    return bytes.fromhex(value.decode("ascii"))


def describe(session: YubiOtpSession) -> int | None:
    state = session.get_config_state()
    try:
        serial = session.get_serial() or None
    except Exception:
        serial = None
    print(
        f"Firmware: {session.version}; serial: {serial if serial else 'unavailable'}; "
        f"slot 1: {'occupied' if state.is_configured(SLOT.ONE) else 'empty'}; "
        f"slot 2: {'occupied' if state.is_configured(SLOT.TWO) else 'empty'}"
    )
    return serial


def confirm(label: str, action: str) -> None:
    expected = f"{action} {label} slot2"
    if action == "replace":
        print(
            "This overwrites the existing slot 2 credential. Slot 1 is preserved.",
            flush=True,
        )
        expected += " and erase existing credential"
    if prompt(f"Check the physical label, then type '{expected}': ") != expected:
        raise RuntimeError("Device confirmation did not match")


def verify_token(session: YubiOtpSession, golden: bytes) -> None:
    if not session.get_config_state().is_configured(SLOT.TWO):
        raise RuntimeError("Slot 2 is empty")
    for challenge in CHALLENGES:
        require_no_response_without_touch(session)
        response = respond(session, challenge)
        expected = hmac.digest(golden, challenge, "sha1")
        if not hmac.compare_digest(response, expected):
            raise RuntimeError("HMAC comparison failed")
    print("PASS: touch gates and three fixed-length challenges match the supplied key.")


def program(
    session: YubiOtpSession, label: str, golden: object, *, replace: bool = False
) -> None:
    if not isinstance(golden, bytes) or len(golden) != 20:
        raise ValueError("Programming requires exactly 20 golden-key bytes")
    occupied = session.get_config_state().is_configured(SLOT.TWO)
    if occupied and not replace:
        print(
            "Stop: slot 2 is occupied. Use verify or explicitly request replacement.",
            file=sys.stderr,
        )
        raise RuntimeError("Refusing an occupied slot")
    confirm(label, "replace" if occupied else "program")
    configuration = (
        HmacSha1SlotConfiguration(golden)
        .lt64(False)
        .require_touch(True)
        .allow_update(False)
    )
    session.put_configuration(SLOT.TWO, configuration)
    print("Slot 2 programmed; slot 1 was not written. Verification follows.")
    verify_token(session, golden)


def verify_set(golden: bytes, labels: Sequence[str]) -> None:
    record = None
    payload = secrets.token_bytes(32)
    seen_serials: set[int] = set()

    def software(challenge: bytes) -> bytes:
        return hmac.digest(golden, challenge, "sha1")

    for label in labels:
        prompt("Remove all YubiKeys, then press Enter: ")
        if list_otp_devices():
            raise RuntimeError("Remove the connected token first")
        prompt(f"Insert only {label}, then press Enter: ")
        with token() as session:
            serial = describe(session)
            if serial and serial in seen_serials:
                raise RuntimeError("This serial was already tested in this set")
            if serial:
                seen_serials.add(serial)
            confirm(label, "verify")
            verify_token(session, golden)
            hardware = partial(respond, session)
            if record is None:
                record = wrapping.wrap(payload, TEST_ID, TEST_ROOT, 1, hardware)
                if not hmac.compare_digest(
                    wrapping.unwrap(record, TEST_ID, TEST_ROOT, software), payload
                ):
                    raise RuntimeError("Software unwrap failed")
            if not hmac.compare_digest(
                wrapping.unwrap(record, TEST_ID, TEST_ROOT, hardware), payload
            ):
                raise RuntimeError("Cross-token unwrap failed")
            print(f"PASS: {label} unwraps the shared in-memory dummy record.")
    print(
        "PASS: all requested labels and the software fallback agree. Record only the non-secret results."
    )


class Arguments(argparse.Namespace):
    command: str
    label: str
    labels: list[str]
    replace: bool


def label(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        raise argparse.ArgumentTypeError("Use a short alphanumeric token label")
    return value


def command(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="homelab-hsm", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generate-key", help="Emit a new 20-byte hex key to a pipe")
    commands.add_parser("inspect", help="Show public device and slot metadata")
    for name in ("program", "verify"):
        operation = commands.add_parser(name)
        operation.add_argument("--label", type=label, required=True)
        if name == "program":
            operation.add_argument("--replace", action="store_true")
    complete = commands.add_parser("verify-set")
    complete.add_argument("--labels", type=label, nargs="+", required=True)
    args = parser.parse_args(argv, namespace=Arguments())
    if args.command == "verify-set" and (
        len(args.labels) < 2 or len(set(args.labels)) != len(args.labels)
    ):
        parser.error("verify-set needs at least two distinct labels")

    harden()
    if args.command == "generate-key":
        generate_key()
        return
    if args.command == "inspect":
        with token() as session:
            describe(session)
        return

    # Establish interactive control and validate the entire secret before USB access.
    require_terminal()
    golden = read_golden_key()
    if args.command == "verify-set":
        verify_set(golden, args.labels)
        return
    with token() as session:
        describe(session)
        if args.command == "program":
            program(session, args.label, golden, replace=args.replace)
        else:
            confirm(args.label, "verify")
            verify_token(session, golden)


def main() -> int:
    sys.dont_write_bytecode = True
    try:
        command()
    except KeyboardInterrupt:
        print(
            "Cancelled; reinsert the token and verify before retrying.", file=sys.stderr
        )
        return 130
    except Exception:
        # Hardware and stream exceptions may contain the key or raw USB traffic.
        print(
            "Failed; secret details suppressed. Check the input pipe, terminal, USB "
            "access and touch. A write may have completed: verify before retrying.",
            file=sys.stderr,
        )
        return 1
    return 0
