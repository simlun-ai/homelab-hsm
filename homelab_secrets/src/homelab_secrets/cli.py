"""Two explicit, memory-only secret workflows; no secret-bearing error output."""

import argparse
import getpass
import hmac
import logging
import os
import stat
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path

from . import wrapping
from .runtime import harden


def parser(command):
    result = argparse.ArgumentParser(prog=command, description=__doc__)
    result.add_argument(
        "--key-id", required=True, help="Expected credential identifier"
    )
    result.add_argument("--root-key", help="Expected root generation, e.g. golden-1")
    result.add_argument(
        "--fake-yubikey",
        action="store_true",
        help="TEST ONLY: use the public software key golden-fake-1",
    )
    return result


FAKE_ROOT = "golden-fake-1"
# Public disposable test material, never a production or recovery key.
FAKE_SECRET = bytes(range(20))


def resolve_root(args, command):
    if args.fake_yubikey:
        if args.root_key not in (None, FAKE_ROOT):
            command.error("--fake-yubikey requires root-key golden-fake-1")
        args.root_key = FAKE_ROOT
    elif args.root_key is None or args.root_key == FAKE_ROOT:
        command.error("Supply --root-key; golden-fake-1 requires --fake-yubikey")


@contextmanager
def fake_responder():
    print(
        "TEST MODE: golden-fake-1 uses a PUBLIC key; anyone can decrypt these records.",
        file=sys.stderr,
        flush=True,
    )
    yield lambda challenge: hmac.digest(FAKE_SECRET, challenge, "sha1")


def selected_responder(args):
    return fake_responder() if args.fake_yubikey else responder()


def require_pipe(stream):
    mode = os.fstat(stream.fileno()).st_mode
    if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        raise ValueError("Plaintext streaming requires a pipe or socket")


def hidden_secret():
    if not sys.stderr.isatty():
        raise ValueError("Hidden input requires a local terminal")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        first = getpass.getpass("Secret (hidden; UTF-8, no appended newline): ")
        second = getpass.getpass("Repeat secret (hidden): ")
    encoded = first.encode("utf-8")
    if len(encoded) > wrapping.MAX_PLAINTEXT or not hmac.compare_digest(
        encoded, second.encode("utf-8")
    ):
        raise ValueError("Secret mismatch or size limit exceeded")
    return encoded


@contextmanager
def responder():
    # Lazy import: library use and --help need no USB SDK initialization.
    from .yubikey import require_no_response_without_touch, respond, token

    with token() as session:
        require_no_response_without_touch(session)
        yield lambda challenge: respond(session, challenge)


def wrap_command(argv=None):
    command = parser("homelab-wrap")
    command.add_argument("--revision", type=int, default=1)
    command.add_argument(
        "--stdin", action="store_true", help="Read exact plaintext bytes from a pipe"
    )
    output = command.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path, help="New ciphertext record path")
    output.add_argument(
        "--stdout", action="store_true", help="Write verified ciphertext to stdout"
    )
    args = command.parse_args(argv)
    resolve_root(args, command)
    harden()
    wrapping.validate_context(args.key_id, args.root_key)
    if not 1 <= args.revision <= 9007199254740991:
        raise ValueError("Invalid revision")
    if args.output is not None and os.path.lexists(args.output):
        raise FileExistsError("Record exists")
    if args.stdin:
        require_pipe(sys.stdin)
        plaintext = sys.stdin.buffer.read(wrapping.MAX_PLAINTEXT + 1)
    else:
        plaintext = hidden_secret()
    if len(plaintext) > wrapping.MAX_PLAINTEXT:
        raise ValueError("Plaintext limit exceeded")
    with selected_responder(args) as respond:
        encoded = wrapping.wrap(
            plaintext, args.key_id, args.root_key, args.revision, respond
        )
        verified = wrapping.unwrap(encoded, args.key_id, args.root_key, respond)
        if not hmac.compare_digest(plaintext, verified):
            raise ValueError("Verification failed")
    if args.stdout:
        sys.stdout.buffer.write(encoded + b"\n")
        sys.stdout.buffer.flush()
    else:
        # Exclusive creation prevents overwrites, including a concurrent creator.
        with args.output.open("xb") as target:
            target.write(encoded + b"\n")
            target.flush()
            os.fsync(target.fileno())
    print("Verified ciphertext record created.", file=sys.stderr)


def unwrap_command(argv=None):
    command = parser("homelab-unwrap")
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Ciphertext record path")
    source.add_argument(
        "--stdin", action="store_true", help="Read ciphertext from stdin"
    )
    output = command.add_mutually_exclusive_group(required=True)
    output.add_argument(
        "--reveal",
        action="store_true",
        help="Confirm display as an escaped bytes literal",
    )
    output.add_argument(
        "--stdout", action="store_true", help="Write exact plaintext bytes to a pipe"
    )
    args = command.parse_args(argv)
    resolve_root(args, command)
    if args.stdin and args.reveal:
        command.error("--stdin requires --stdout; reveal needs stdin for confirmation")
    harden()
    if args.stdout:
        require_pipe(sys.stdout)
    elif not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise ValueError("Reveal requires a local terminal")
    if args.stdin:
        encoded = sys.stdin.buffer.read(wrapping.MAX_RECORD + 1)
    else:
        with args.input.open("rb") as source:
            encoded = source.read(wrapping.MAX_RECORD + 1)
    # Reject malformed records and substituted contexts before even opening USB.
    wrapping.parse_record(encoded, args.key_id, args.root_key)
    if args.reveal:
        print(
            "Display secret in this unrecorded terminal? Type reveal:",
            file=sys.stderr,
            flush=True,
        )
        if sys.stdin.readline().rstrip("\n") != "reveal":
            raise ValueError("Reveal cancelled")
    with selected_responder(args) as respond:
        plaintext = wrapping.unwrap(encoded, args.key_id, args.root_key, respond)
    if args.stdout:
        sys.stdout.buffer.write(plaintext)
        sys.stdout.buffer.flush()
    else:
        # Escape control sequences rather than executing arbitrary terminal bytes.
        print(repr(plaintext))


def run(command):
    logging.disable(sys.maxsize)
    sys.dont_write_bytecode = True
    try:
        command()
    except KeyboardInterrupt:
        print("Cancelled; reinsert the token before retrying.", file=sys.stderr)
        return 130
    except Exception:
        # USB, crypto, and consumer errors can contain secret-bearing details.
        print(
            "Failed; secret details suppressed. Check context, record path, stream mode, "
            "USB access, and touch. Existing records are never overwritten.",
            file=sys.stderr,
        )
        return 1
    return 0


def wrap_main():
    return run(wrap_command)


def unwrap_main():
    return run(unwrap_command)
