"""Read-only slot 2 HMAC access; this module cannot program a token."""

import sys
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from threading import Event, Timer
from typing import cast

from ykman.hid import list_otp_devices
from yubikit.core import TimeoutError as TokenTimeout
from yubikit.core.otp import STATUS_UPNEEDED, OtpConnection
from yubikit.yubiotp import SLOT, YubiOtpSession


@contextmanager
def token() -> Generator[YubiOtpSession, None, None]:
    devices = list_otp_devices()
    if len(devices) != 1:
        print("Connect exactly one accessible OTP-capable YubiKey.", file=sys.stderr)
        raise RuntimeError("Ambiguous or unavailable device")
    open_otp = cast(
        Callable[[type[OtpConnection]], AbstractContextManager[OtpConnection]],
        devices[0].open_connection,  # pyright: ignore[reportUnknownMemberType] -- SDK generic lacks annotations
    )
    with open_otp(OtpConnection) as connection:
        session = YubiOtpSession(connection)
        if session.version < (2, 2, 0):
            raise RuntimeError("Firmware lacks HMAC challenge-response")
        yield session


def require_no_response_without_touch(session: YubiOtpSession) -> None:
    print(
        "Do NOT touch: checking that a request waits for physical touch.",
        flush=True,
        file=sys.stderr,
    )
    cancel, requested_touch = Event(), Event()

    def keepalive(status: int) -> None:
        if status == STATUS_UPNEEDED:
            requested_touch.set()
            cancel.set()

    timer = Timer(5, cancel.set)
    timer.start()
    try:
        session.calculate_hmac_sha1(SLOT.TWO, b"A" * 64, cancel, keepalive)
    except TokenTimeout:
        if not requested_touch.is_set():
            raise RuntimeError(
                "Timeout without proof that touch was required"
            ) from None
    else:
        raise RuntimeError("Received a response without the required touch gate")
    finally:
        timer.cancel()
        timer.join()


def respond(session: YubiOtpSession, challenge: bytes) -> bytes:
    if len(challenge) != 64:
        raise ValueError("Only fixed 64-byte challenges are allowed")
    print("Touch the connected YubiKey when it flashes.", flush=True, file=sys.stderr)
    cancel = Event()
    timer = Timer(20, cancel.set)
    timer.start()
    try:
        response = session.calculate_hmac_sha1(SLOT.TWO, challenge, cancel)
    finally:
        timer.cancel()
        timer.join()
    if len(response) != 20:
        raise RuntimeError("Invalid response size")
    return response
