"""Mocked OTP hardware; no real token or golden key is used."""
from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import MagicMock, Mock, patch

from yubikit.yubiotp import SLOT
from homelab_secrets import yubikey


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.err = self.enterContext(redirect_stderr(io.StringIO()))
        self.out = self.enterContext(redirect_stdout(io.StringIO()))

    def test_missing_or_multiple_tokens_rejected(self):
        for devices in ([], [Mock(), Mock()]):
            with patch.object(yubikey, 'list_otp_devices', return_value=devices), self.assertRaises(RuntimeError):
                with yubikey.token():
                    self.fail('Ambiguous device must not be selected')

    def test_token_connection_is_closed_and_firmware_checked(self):
        device = Mock()
        connection = Mock()
        manager = MagicMock()
        manager.__enter__.return_value = connection
        device.open_connection.return_value = manager
        with patch.object(yubikey, 'list_otp_devices', return_value=[device]), \
                patch.object(yubikey, 'YubiOtpSession', return_value=self.session):
            self.session.version = (2, 2, 0)
            with yubikey.token() as selected:
                self.assertIs(selected, self.session)
            self.session.version = (2, 1, 9)
            with self.assertRaises(RuntimeError), yubikey.token():
                pass
        self.assertEqual(manager.__exit__.call_count, 2)

    def test_response_uses_slot_two_and_status_only_on_stderr(self):
        self.session.calculate_hmac_sha1.return_value = b'r' * 20
        with patch.object(yubikey, 'Timer') as timer:
            self.assertEqual(yubikey.respond(self.session, b'A' * 64), b'r' * 20)
        self.assertEqual(self.session.calculate_hmac_sha1.call_args.args[0], SLOT.TWO)
        timer.return_value.start.assert_called_once()
        timer.return_value.cancel.assert_called_once()
        timer.return_value.join.assert_called_once()
        self.assertEqual(self.out.getvalue(), '')
        self.assertIn('Touch', self.err.getvalue())
        self.assertNotIn('r' * 20, self.err.getvalue())

    def test_bad_challenge_never_queries_hardware(self):
        with self.assertRaises(ValueError):
            yubikey.respond(self.session, b'short')
        self.session.calculate_hmac_sha1.assert_not_called()

    def test_response_size_and_exception_cleanup(self):
        self.session.calculate_hmac_sha1.return_value = b'short'
        with self.assertRaises(RuntimeError):
            yubikey.respond(self.session, b'A' * 64)
        self.session.calculate_hmac_sha1.side_effect = yubikey.TokenTimeout('dummy private detail')
        with patch.object(yubikey, 'Timer') as timer, self.assertRaises(yubikey.TokenTimeout):
            yubikey.respond(self.session, b'A' * 64)
        timer.return_value.cancel.assert_called_once()
        timer.return_value.join.assert_called_once()

    def test_no_touch_probe_rejects_immediate_response(self):
        self.session.calculate_hmac_sha1.return_value = b'r' * 20
        with self.assertRaises(RuntimeError):
            yubikey.require_no_response_without_touch(self.session)

    def test_no_touch_probe_requires_actual_touch_request(self):
        self.session.calculate_hmac_sha1.side_effect = yubikey.TokenTimeout('dummy private detail')
        with self.assertRaises(RuntimeError):
            yubikey.require_no_response_without_touch(self.session)

    def test_no_touch_probe_cancels_confirmed_touch_request(self):
        def pending(slot, challenge, event, keepalive):
            self.assertEqual(slot, SLOT.TWO)
            keepalive(yubikey.STATUS_UPNEEDED)
            self.assertTrue(event.is_set())
            raise yubikey.TokenTimeout('dummy private detail')
        self.session.calculate_hmac_sha1.side_effect = pending
        yubikey.require_no_response_without_touch(self.session)
        self.assertNotIn('dummy private detail', self.err.getvalue())
