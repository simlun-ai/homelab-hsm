"""Public dummy secrets only. USB and process hardening are mocked explicitly."""
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
import hmac
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from homelab_secrets import cli, wrapping

ID = 'homelab/v1/test/wrapping/fixture/r1'
ROOT = 'test-only'
CONTEXT = ['--key-id', ID, '--root-key', ROOT]
PAYLOAD = b'public dummy\x00\xff\n'


def respond(challenge):
    return hmac.digest(bytes(range(20)), challenge, 'sha1')


class CliTests(unittest.TestCase):
    def setUp(self):
        self.contexts = ExitStack()
        self.addCleanup(self.contexts.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'record.json'
        self.harden = self.contexts.enter_context(patch.object(cli, 'harden'))
        self.token = self.contexts.enter_context(patch.object(cli, 'responder', side_effect=lambda: nullcontext(respond)))
        self.err = self.contexts.enter_context(redirect_stderr(io.StringIO()))

    def record(self):
        self.path.write_bytes(wrapping.wrap(PAYLOAD, ID, ROOT, 1, respond))

    def wrap(self, *args):
        cli.wrap_command(CONTEXT + ['--output', str(self.path), *args])

    def unwrap(self, *args):
        cli.unwrap_command(CONTEXT + ['--input', str(self.path), *args])

    def test_wrap_verified_ciphertext_and_no_secret_output(self):
        with patch.object(cli, 'hidden_secret', return_value=PAYLOAD), redirect_stdout(io.StringIO()) as out:
            self.wrap()
        self.assertEqual(wrapping.unwrap(self.path.read_bytes(), ID, ROOT, respond), PAYLOAD)
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn('public dummy', self.err.getvalue())
        self.harden.assert_called_once()

    def test_wrap_never_overwrites_before_token_or_input(self):
        self.record()
        original = self.path.read_bytes()
        with patch.object(cli, 'hidden_secret') as hidden, self.assertRaises(FileExistsError):
            self.wrap()
        self.token.assert_not_called()
        hidden.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)

    def test_wrap_verification_failure_writes_nothing(self):
        with patch.object(cli, 'hidden_secret', return_value=PAYLOAD), \
                patch.object(wrapping, 'unwrap', return_value=b'wrong'), self.assertRaises(ValueError):
            self.wrap()
        self.assertFalse(self.path.exists())

    def test_concurrent_creator_is_not_overwritten(self):
        def create():
            self.path.write_bytes(b'other ciphertext')
            return nullcontext(respond)
        self.token.side_effect = create
        with patch.object(cli, 'hidden_secret', return_value=PAYLOAD), self.assertRaises(FileExistsError):
            self.wrap()
        self.assertEqual(self.path.read_bytes(), b'other ciphertext')

    def test_stdin_preserves_binary_and_newlines(self):
        reader, writer = os.pipe()
        with os.fdopen(writer, 'wb') as output:
            output.write(PAYLOAD)
        with os.fdopen(reader, 'r') as source, patch.object(cli.sys, 'stdin', source):
            self.wrap('--stdin')
        self.assertEqual(wrapping.unwrap(self.path.read_bytes(), ID, ROOT, respond), PAYLOAD)

    def test_oversize_input_fails_before_token(self):
        source = Mock(buffer=io.BytesIO(b'x' * (wrapping.MAX_PLAINTEXT + 1)))
        with patch.object(cli.sys, 'stdin', source), patch.object(cli, 'require_pipe'), self.assertRaises(ValueError):
            self.wrap('--stdin')
        self.token.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_unwrap_requires_output_selection(self):
        with self.assertRaises(SystemExit):
            self.unwrap()
        self.token.assert_not_called()

    def test_invalid_context_fails_before_usb(self):
        self.record()
        with patch.object(cli, 'require_pipe'), self.assertRaises(ValueError):
            cli.unwrap_command(['--key-id', ID.replace('fixture', 'other'), '--root-key', ROOT,
                                '--input', str(self.path), '--stdout'])
        self.token.assert_not_called()

    def test_malformed_record_fails_before_usb(self):
        self.path.write_bytes(b'{}')
        with patch.object(cli, 'require_pipe'), self.assertRaises(ValueError):
            self.unwrap('--stdout')
        self.token.assert_not_called()

    def test_stdout_streams_exact_bytes_without_status(self):
        self.record()
        reader, writer = os.pipe()
        with os.fdopen(writer, 'w') as target, patch.object(cli.sys, 'stdout', target):
            self.unwrap('--stdout')
        with os.fdopen(reader, 'rb') as source:
            self.assertEqual(source.read(), PAYLOAD)

    def test_stdout_rejects_file_before_usb(self):
        self.record()
        with tempfile.TemporaryFile(mode='w+') as target, patch.object(cli.sys, 'stdout', target):
            with self.assertRaises(ValueError):
                self.unwrap('--stdout')
            target.seek(0)
            self.assertEqual(target.read(), '')
        self.token.assert_not_called()

    def test_reveal_requires_confirmation_and_escapes_terminal_bytes(self):
        self.record()
        source, target, error = io.StringIO('reveal\n'), io.StringIO(), io.StringIO()
        for stream in (source, target, error):
            stream.isatty = lambda: True
        with patch.object(cli.sys, 'stdin', source), patch.object(cli.sys, 'stdout', target), \
                patch.object(cli.sys, 'stderr', error):
            self.unwrap('--reveal')
        self.assertEqual(target.getvalue(), repr(PAYLOAD) + '\n')
        self.assertIn('Type reveal', error.getvalue())

    def test_hidden_input_utf8_confirmation_and_no_fallback(self):
        with patch.object(cli.sys.stderr, 'isatty', return_value=True), \
                patch.object(cli.getpass, 'getpass', side_effect=['dummy é', 'dummy é']):
            self.assertEqual(cli.hidden_secret(), 'dummy é'.encode())
        with patch.object(cli.sys.stderr, 'isatty', return_value=True), \
                patch.object(cli.getpass, 'getpass', side_effect=['one', 'two']), self.assertRaises(ValueError):
            cli.hidden_secret()

    def test_failures_suppress_exception_details(self):
        self.assertEqual(cli.run(Mock(side_effect=RuntimeError('private USB traffic'))), 1)
        self.assertNotIn('private USB traffic', self.err.getvalue())
        self.assertEqual(cli.run(Mock(side_effect=KeyboardInterrupt)), 130)

    def test_revision_validation_precedes_token(self):
        for revision in ('0', '-1', '9007199254740992'):
            with self.assertRaises(ValueError):
                self.wrap('--revision', revision)
        self.token.assert_not_called()

