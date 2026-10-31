"""Disposable public test material only. No real token or golden key required."""

import io
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from yubikit.yubiotp import SLOT

from homelab_secrets import setup

PUBLIC_TEST_KEY = bytes(range(20))


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock()
        self.session.get_config_state.return_value.is_configured.return_value = False
        self.output = io.StringIO()

    def test_program_refuses_occupied_slot_before_confirmation(self) -> None:
        self.session.get_config_state.return_value.is_configured.return_value = True
        with patch.object(setup, "confirm") as confirm, self.assertRaises(RuntimeError):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY)
        confirm.assert_not_called()
        self.session.put_configuration.assert_not_called()

    def test_replacement_requires_full_erase_confirmation(self) -> None:
        self.session.get_config_state.return_value.is_configured.return_value = True
        for answer in (
            "program key0 slot2",
            "replace key0 slot2",
            "replace key1 slot2 and erase existing credential",
        ):
            with (
                self.subTest(answer=answer),
                patch.object(setup, "prompt", return_value=answer),
                patch.object(setup, "verify_token") as verify,
                redirect_stdout(self.output),
            ):
                with self.assertRaises(RuntimeError):
                    setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=True)
                self.session.put_configuration.assert_not_called()
                verify.assert_not_called()

    def test_replacement_writes_only_slot_two_then_verifies(self) -> None:
        self.session.get_config_state.return_value.is_configured.return_value = True
        operations: list[str] = []

        def wrote(*args: object) -> None:
            operations.append("write")

        def verified(*args: object) -> None:
            operations.append("verify")

        self.session.put_configuration.side_effect = wrote
        with (
            patch.object(
                setup,
                "prompt",
                return_value="replace key0 slot2 and erase existing credential",
            ) as prompt,
            patch.object(
                setup,
                "verify_token",
                side_effect=verified,
            ) as verify,
            redirect_stdout(self.output),
        ):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY, replace=True)
        self.assertIn(
            "replace key0 slot2 and erase existing credential", prompt.call_args.args[0]
        )
        self.session.put_configuration.assert_called_once()
        self.assertEqual(self.session.put_configuration.call_args.args[0], SLOT.TWO)
        self.assertEqual(operations, ["write", "verify"])
        verify.assert_called_once_with(self.session, PUBLIC_TEST_KEY)
        self.assertIn(
            "overwrites the existing slot 2 credential", self.output.getvalue()
        )
        self.assertNotIn(PUBLIC_TEST_KEY.hex(), self.output.getvalue())

    def test_cli_passes_explicit_replacement_to_program(self) -> None:
        self.session.get_config_state.return_value.is_configured.return_value = True
        with (
            patch.object(
                setup.sys,
                "argv",
                ["yubikey_cli", "program", "--label", "key0", "--replace"],
            ),
            patch.object(setup, "harden"),
            patch.object(setup, "require_terminal"),
            patch.object(setup, "describe"),
            patch.object(setup, "token", return_value=nullcontext(self.session)),
            patch.object(setup, "read_golden_key", return_value=PUBLIC_TEST_KEY),
            patch.object(setup, "program") as program,
        ):
            setup.command()
        program.assert_called_once_with(
            self.session, "key0", PUBLIC_TEST_KEY, replace=True
        )

    def test_cli_replacement_flag_rejected_before_hardware_for_other_commands(
        self,
    ) -> None:
        for command in ("inspect", "verify", "verify-set"):
            with (
                self.subTest(command=command),
                patch.object(
                    setup.sys,
                    "argv",
                    ["yubikey_cli", command, "--label", "key0", "--replace"],
                ),
                patch.object(setup, "harden") as harden,
                patch.object(setup, "token") as token,
                redirect_stderr(self.output),
            ):
                with self.assertRaises(SystemExit) as error:
                    setup.command()
                self.assertEqual(error.exception.code, 2)
                harden.assert_not_called()
                token.assert_not_called()

    def test_program_rejects_wrong_key_length_without_writing(self) -> None:
        for golden in (b"short", b"x" * 21):
            with self.assertRaises(ValueError):
                setup.program(self.session, "key0", golden)
        self.session.put_configuration.assert_not_called()

    def test_program_targets_slot_two_with_fixed_input_and_touch(self) -> None:
        for occupied in (False, True):
            with self.subTest(occupied=occupied):
                self.session.reset_mock()
                self.session.get_config_state.return_value.is_configured.return_value = occupied
                with (
                    patch.object(setup, "confirm"),
                    patch.object(setup, "verify_token") as verify,
                    redirect_stdout(self.output),
                ):
                    setup.program(
                        self.session, "key0", PUBLIC_TEST_KEY, replace=occupied
                    )
                args = self.session.put_configuration.call_args.args
                self.assertEqual(args[0], SLOT.TWO)
                encoded = args[1].get_config()
                # OTP config: fixed-size[44], extended[45], ticket[46], config[47].
                self.assertTrue(encoded[46] & 0x40)  # CHAL_RESP
                self.assertTrue(encoded[47] & 0x02)  # HMAC mode (0x22)
                self.assertTrue(encoded[47] & 0x08)  # CHAL_BTN_TRIG
                self.assertFalse(encoded[47] & 0x04)  # HMAC_LT64 must be clear
                self.assertFalse(encoded[45] & 0x20)  # ALLOW_UPDATE disabled
                self.session.put_configuration.assert_called_once()
                verify.assert_called_once_with(self.session, PUBLIC_TEST_KEY)
                self.assertNotIn(PUBLIC_TEST_KEY.hex(), self.output.getvalue())

    def test_input_preserves_leading_zeros_and_rejects_extra_data(self) -> None:
        for value in (b"00" * 2 + b"a1" * 18, b"00" * 2 + b"A1" * 18 + b"\n"):
            with (
                patch.object(setup, "require_pipe"),
                patch.object(setup.sys, "stdin", Mock(buffer=io.BytesIO(value))),
            ):
                self.assertEqual(setup.read_golden_key(), bytes.fromhex(value.decode()))
        for value in (
            b"",
            b"short",
            b"x" * 40,
            b"a" * 39,
            b"a" * 41,
            b"a" * 40 + b"\nmetadata",
            b"a" * 40 + b"\n\n",
            b"a" * 1000,
        ):
            with (
                self.subTest(length=len(value)),
                patch.object(setup, "require_pipe"),
                patch.object(setup.sys, "stdin", Mock(buffer=io.BytesIO(value))),
                self.assertRaises(ValueError),
            ):
                setup.read_golden_key()

    def test_bad_input_never_opens_hardware(self) -> None:
        with (
            patch.object(setup, "harden"),
            patch.object(setup, "require_terminal"),
            patch.object(setup, "read_golden_key", side_effect=ValueError),
            patch.object(setup, "token") as token,
            self.assertRaises(ValueError),
        ):
            setup.command(["program", "--label", "spare"])
        token.assert_not_called()

    def test_missing_terminal_never_reads_key_or_opens_hardware(self) -> None:
        with (
            patch.object(setup, "harden"),
            patch.object(setup, "require_terminal", side_effect=OSError),
            patch.object(setup, "read_golden_key") as read,
            patch.object(setup, "token") as token,
            self.assertRaises(OSError),
        ):
            setup.command(["program", "--label", "spare"])
        read.assert_not_called()
        token.assert_not_called()

    def test_generation_only_writes_key_to_pipe(self) -> None:
        with (
            patch.object(setup, "require_pipe") as pipe,
            patch.object(
                setup.secrets, "token_hex", return_value=PUBLIC_TEST_KEY.hex()
            ) as rng,
            redirect_stdout(self.output),
        ):
            setup.generate_key()
        pipe.assert_called_once()
        rng.assert_called_once_with(20)
        self.assertEqual(self.output.getvalue(), PUBLIC_TEST_KEY.hex() + "\n")

    def test_error_does_not_disclose_secret(self) -> None:
        with (
            patch.object(
                setup, "command", side_effect=RuntimeError(PUBLIC_TEST_KEY.hex())
            ),
            redirect_stderr(self.output),
        ):
            self.assertEqual(setup.main(), 1)
        self.assertNotIn(PUBLIC_TEST_KEY.hex(), self.output.getvalue())

    def test_verify_set_rejects_duplicate_labels_before_usb(self) -> None:
        with (
            patch.object(setup, "harden") as harden,
            redirect_stderr(self.output),
            self.assertRaises(SystemExit),
        ):
            setup.command(["verify-set", "--labels", "spare", "spare"])
        harden.assert_not_called()

    def test_verify_set_uses_requested_labels_and_rejects_repeated_serial(self) -> None:
        def response(session: object, challenge: bytes) -> bytes:
            return setup.hmac.digest(PUBLIC_TEST_KEY, challenge, "sha1")

        self.session.get_serial.return_value = 123
        self.session.get_config_state.return_value.is_configured.return_value = True
        with (
            patch.object(setup, "prompt", return_value="") as prompt,
            patch.object(setup, "confirm"),
            patch.object(setup, "list_otp_devices", return_value=[]),
            patch.object(setup, "token", return_value=nullcontext(self.session)),
            patch.object(setup, "verify_token"),
            patch.object(
                setup,
                "respond",
                side_effect=response,
            ),
            redirect_stdout(self.output),
            self.assertRaisesRegex(RuntimeError, "already tested"),
        ):
            setup.verify_set(PUBLIC_TEST_KEY, ["primary", "spare"])
        self.assertIn("Insert only spare", str(prompt.call_args_list))

    def test_occupied_slot_one_does_not_block_programming_slot_two(self) -> None:
        def configured(slot: SLOT) -> bool:
            return slot == SLOT.ONE

        self.session.get_config_state.return_value.is_configured.side_effect = (
            configured
        )
        with (
            patch.object(setup, "confirm"),
            patch.object(setup, "verify_token"),
            redirect_stdout(self.output),
        ):
            setup.program(self.session, "key0", PUBLIC_TEST_KEY)
        self.assertEqual(self.session.put_configuration.call_args.args[0], SLOT.TWO)

    def test_old_slot_one_confirmation_is_rejected(self) -> None:
        with (
            patch.object(setup, "prompt", return_value="program key0 slot1"),
            self.assertRaises(RuntimeError),
        ):
            setup.confirm("key0", "program")

    def test_verify_rejects_wrong_golden_key(self) -> None:
        self.session.get_config_state.return_value.is_configured.return_value = True
        with (
            patch.object(setup, "require_no_response_without_touch"),
            patch.object(setup, "respond", return_value=b"x" * 20),
            self.assertRaises(RuntimeError),
        ):
            setup.verify_token(self.session, PUBLIC_TEST_KEY)


if __name__ == "__main__":
    unittest.main()
