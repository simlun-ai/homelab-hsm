"""Explicit process hardening; applications must opt in before handling secrets."""
import ctypes
import logging
import resource
import sys


def harden(*, require_terminal=False):
    logging.disable(sys.maxsize)
    if sys.platform != "linux":
        raise RuntimeError("Secret operations require Linux")
    if require_terminal and not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise RuntimeError("Use a local Linux terminal without redirection")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_DUMPABLE=0 also prevents ordinary same-user ptrace/proc memory access.
    if libc.prctl(4, 0, 0, 0, 0) != 0:
        raise RuntimeError("Cannot disable process dumping")
