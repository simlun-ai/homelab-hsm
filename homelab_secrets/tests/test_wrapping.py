"""Disposable public test material only; no hardware required."""
import base64
import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock
from cryptography.exceptions import InvalidTag
from homelab_secrets import wrapping

PUBLIC_TEST_KEY = bytes(range(20))
ID = "homelab/v1/test/wrapping/fixture/r1"
ROOT = "test-only"

def software(challenge):
    return hmac.digest(PUBLIC_TEST_KEY, challenge, "sha1")

class WrappingTests(unittest.TestCase):
    def setUp(self):
        self.record = wrapping.wrap(b"disposable dummy", ID, ROOT, 1, software)

    def rewrite(self, **changes):
        data = json.loads(self.record)
        data.update(changes)
        return json.dumps(data).encode()

    def test_hmac_rfc2202_vector_and_challenge(self):
        self.assertEqual(hmac.digest(b"\x0b" * 20, b"Hi There", "sha1").hex(),
                         "b617318655057264e28bc0b6fb378c8ef146be00")
        self.assertEqual(wrapping.challenge(ID), hashlib.sha256(ID.encode()).hexdigest().encode())
        self.assertEqual(len(wrapping.challenge(ID)), 64)

    def test_known_hkdf_info_and_header_encoding(self):
        header = {"format": "homelab-wrap-v1", "key_id": ID, "root_key": ROOT,
                  "revision": 9007199254740991, "salt": "ab/+==", "nonce": "cd/+=="}
        expected = ('{"format":"homelab-wrap-v1","key_id":"' + ID +
                    '","nonce":"cd/+==","revision":9007199254740991,"root_key":"test-only","salt":"ab/+=="}').encode()
        self.assertEqual(wrapping.canonical_header(header), expected)
        # Independent RFC 5869 extract/expand for the format's actual context.
        salt = bytes(range(32))
        prk = hmac.digest(salt, b"r" * 20, "sha256")
        expected_key = hmac.digest(prk, b"homelab-wrap-v1\0test-only\0" + ID.encode() + b"\x01", "sha256")
        self.assertEqual(wrapping.derive(b"r" * 20, salt, ROOT, ID), expected_key)

    def test_roundtrip_uses_fresh_salt_and_nonce(self):
        other = json.loads(wrapping.wrap(b"disposable dummy", ID, ROOT, 1, software))
        first = json.loads(self.record)
        self.assertNotEqual(other["salt"], first["salt"])
        self.assertNotEqual(other["nonce"], first["nonce"])
        self.assertEqual(wrapping.unwrap(self.record, ID, ROOT, software), b"disposable dummy")

    def test_validation_precedes_token_access(self):
        missing = json.loads(self.record)
        del missing["salt"]
        invalid = [b"[]", b"{", b"{" + self.record[1:-1] + b',"revision":2}',
                   json.dumps(missing).encode(), self.rewrite(extra="field"),
                   self.rewrite(revision=True), self.rewrite(revision=0),
                   self.rewrite(revision=9007199254740992), self.rewrite(revision=1.0),
                   self.rewrite(format="unknown"), self.rewrite(key_id=ID + "/wrong"),
                   self.rewrite(root_key="wrong"), self.rewrite(salt="abc"),
                   self.rewrite(nonce=base64.b64encode(b"n" * 11).decode()),
                   self.rewrite(ciphertext=base64.b64encode(b"x" * 15).decode()),
                   self.rewrite(salt=json.loads(self.record)["salt"] + "\n"),
                   b" " * (wrapping.MAX_RECORD + 1)]
        for encoded in invalid:
            with self.subTest(length=len(encoded)):
                responder = Mock(side_effect=AssertionError("Token must not be queried"))
                with self.assertRaises(ValueError):
                    wrapping.unwrap(encoded, ID, ROOT, responder)
                responder.assert_not_called()

    def test_authenticated_fields_and_ciphertext_tampering(self):
        data = json.loads(self.record)
        for field in ("salt", "nonce", "ciphertext"):
            raw = bytearray(base64.b64decode(data[field]))
            raw[0] ^= 1
            with self.subTest(field=field), self.assertRaises(InvalidTag):
                wrapping.unwrap(self.rewrite(**{field: base64.b64encode(raw).decode()}), ID, ROOT, software)
        with self.assertRaises(InvalidTag):
            wrapping.unwrap(self.rewrite(revision=2), ID, ROOT, software)
        with self.assertRaises(InvalidTag):
            wrapping.unwrap(self.record, ID, ROOT, lambda _: b"x" * 20)

    def test_context_and_input_limits(self):
        for bad in (ID.upper(), ID + "\n", ID.replace("fixture", ""), ID.replace("/r1", "/r0")):
            with self.subTest(identifier=bad), self.assertRaises(ValueError):
                wrapping.challenge(bad)
        with self.assertRaises(ValueError):
            wrapping.wrap(b"x" * (wrapping.MAX_PLAINTEXT + 1), ID, ROOT, 1, software)
        with self.assertRaises(ValueError):
            wrapping.wrap(b"test", ID, ROOT, 1, lambda _: b"short")

    def test_record_from_original_parent_implementation(self):
        encoded = b'{"ciphertext":"sadXBJnrRzpWuoegCGM/qh3UNgNRTaUuyZKo+A/H","format":"homelab-wrap-v1","key_id":"homelab/v1/test/wrapping/fixture/r1","nonce":"7WLa8+YuRdXmzT5q","revision":1,"root_key":"test-only","salt":"SGQXoR1g8AQlo1WgSc2TQHCdBPmCgwntiHDo/bH30oI="}'
        self.assertEqual(wrapping.unwrap(encoded, ID, ROOT, software), b"legacy fixture")
