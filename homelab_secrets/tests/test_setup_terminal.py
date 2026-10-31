"""Exercise a real controlling terminal with independent piped secret input."""

import fcntl
import os
import pty
import select
import subprocess
import sys
import termios
import unittest


class TerminalTests(unittest.TestCase):
    def test_confirmation_uses_tty_and_leaves_stdin_untouched(self) -> None:
        master, slave = pty.openpty()

        def terminal_session() -> None:
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

        try:
            with subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "from homelab_secrets.setup import require_terminal, prompt; "
                        "import sys; require_terminal(); "
                        "assert prompt('Confirm: ') == 'yes'; "
                        "assert sys.stdin.buffer.read() == b'public-pipe-fixture'; "
                        "print('confirmed')"
                    ),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(slave,),
                preexec_fn=terminal_session,
            ) as process:
                try:
                    ready, _, _ = select.select([master], [], [], 10)
                    self.assertTrue(ready, "No terminal prompt")
                    self.assertIn(b"Confirm: ", os.read(master, 1024))
                    os.write(master, b"yes\n")
                    stdout, stderr = process.communicate(
                        b"public-pipe-fixture", timeout=10
                    )
                    self.assertEqual(process.returncode, 0, stderr.decode())
                    self.assertEqual(stdout, b"confirmed\n")
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
        finally:
            os.close(master)
            os.close(slave)
