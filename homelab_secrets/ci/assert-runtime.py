"""Check that CI uses the distro's expected interpreter without PC/SC."""

import ctypes
import sys

actual = f"{sys.version_info.major}.{sys.version_info.minor}"
if actual != sys.argv[1]:
    raise SystemExit(f"Expected Python {sys.argv[1]}, found {actual}")
try:
    ctypes.CDLL("libpcsclite.so.1")
except OSError:
    pass
else:
    raise SystemExit("CI must validate installation without PC/SC")
