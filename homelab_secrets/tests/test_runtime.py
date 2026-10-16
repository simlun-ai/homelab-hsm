"""Process policy is explicit and independently testable."""
import unittest
from unittest.mock import Mock, patch
from homelab_secrets import runtime


class RuntimeTests(unittest.TestCase):
    def test_linux_dumps_disabled_without_requiring_terminal_for_pipes(self):
        with patch.object(runtime.sys, 'platform', 'linux'), \
                patch.object(runtime.resource, 'setrlimit') as limit, \
                patch.object(runtime.ctypes, 'CDLL') as libc, \
                patch.object(runtime.logging, 'disable'):
            libc.return_value.prctl.return_value = 0
            runtime.harden()
            limit.assert_called_once_with(runtime.resource.RLIMIT_CORE, (0, 0))
            libc.return_value.prctl.assert_called_once_with(4, 0, 0, 0, 0)

    def test_hardening_fails_closed(self):
        with patch.object(runtime.sys, 'platform', 'not-linux'), self.assertRaises(RuntimeError):
            runtime.harden()
        with patch.object(runtime.sys, 'platform', 'linux'), \
                patch.object(runtime.sys, 'stdin', Mock(isatty=lambda: False)), self.assertRaises(RuntimeError):
            runtime.harden(require_terminal=True)
        with patch.object(runtime.sys, 'platform', 'linux'), \
                patch.object(runtime.resource, 'setrlimit'), patch.object(runtime.ctypes, 'CDLL') as libc:
            libc.return_value.prctl.return_value = -1
            with self.assertRaises(RuntimeError):
                runtime.harden()
