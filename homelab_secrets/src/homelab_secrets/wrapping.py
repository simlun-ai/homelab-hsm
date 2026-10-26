"""The constrained homelab-wrap-v1 format; never log plaintext or responses."""

import base64
import hashlib
import json
import re
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

FORMAT = "homelab-wrap-v1"
MAX_PLAINTEXT = 1024 * 1024
MAX_RECORD = 2 * 1024 * 1024
MAX_IDENTIFIER = 1024
MAX_ROOT = 64
FIELDS = {"format", "root_key", "key_id", "revision", "salt", "nonce", "ciphertext"}
IDENTIFIER = re.compile(
    r"homelab/v1/[a-z0-9-]+/[a-z0-9-]+/(?:[a-z0-9-]+/)+r[1-9][0-9]*", re.ASCII
)
ROOT = re.compile(r"[a-z0-9-]+", re.ASCII)


def validate_context(key_id, root_key):
    if (
        not isinstance(key_id, str)
        or len(key_id) > MAX_IDENTIFIER
        or not IDENTIFIER.fullmatch(key_id)
    ):
        raise ValueError("Invalid credential identifier")
    if (
        not isinstance(root_key, str)
        or len(root_key) > MAX_ROOT
        or not ROOT.fullmatch(root_key)
    ):
        raise ValueError("Invalid root-key generation")


def challenge(key_id):
    validate_context(key_id, "validation")
    return hashlib.sha256(key_id.encode("ascii")).hexdigest().encode("ascii")


def canonical_header(header):
    # Validated headers contain only ASCII strings from restricted alphabets and
    # integers <= 2**53-1. Sorted compact JSON is RFC 8785 JCS for this subset.
    return json.dumps(
        header, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def derive(response, salt, root_key, key_id):
    if not isinstance(response, bytes) or len(response) != 20:
        raise ValueError("Expected a 20-byte HMAC response")
    info = b"\0".join(x.encode("ascii") for x in (FORMAT, root_key, key_id))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(
        response
    )


def _b64(value):
    return base64.b64encode(value).decode("ascii")


def _decode(value, minimum, maximum):
    if not isinstance(value, str) or len(value) > 4 * ((maximum + 2) // 3):
        raise ValueError("Invalid encoded field")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid Base64") from exc
    if not minimum <= len(raw) <= maximum or _b64(raw) != value:
        raise ValueError("Invalid field size or noncanonical Base64")
    return raw


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate record field")
        result[key] = value
    return result


def parse_record(encoded, key_id, root_key):
    """Validate the complete public record before asking a token for a response."""
    validate_context(key_id, root_key)
    if not isinstance(encoded, bytes) or len(encoded) > MAX_RECORD:
        raise ValueError("Record exceeds limit or is not bytes")
    record = json.loads(encoded, object_pairs_hook=_unique)
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("Unexpected record fields")
    if (
        record["format"] != FORMAT
        or record["key_id"] != key_id
        or record["root_key"] != root_key
    ):
        raise ValueError("Record context mismatch")
    revision = record["revision"]
    if type(revision) is not int or not 1 <= revision <= 9007199254740991:
        raise ValueError("Invalid revision")
    salt = _decode(record["salt"], 32, 32)
    nonce = _decode(record["nonce"], 12, 12)
    ciphertext = _decode(record["ciphertext"], 16, MAX_PLAINTEXT + 16)
    header = {key: value for key, value in record.items() if key != "ciphertext"}
    return header, salt, nonce, ciphertext


def wrap(plaintext, key_id, root_key, revision, respond):
    validate_context(key_id, root_key)
    if not isinstance(plaintext, bytes) or len(plaintext) > MAX_PLAINTEXT:
        raise ValueError("Plaintext exceeds limit or is not bytes")
    if type(revision) is not int or not 1 <= revision <= 9007199254740991:
        raise ValueError("Invalid revision")
    salt, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
    header = dict(
        format=FORMAT,
        root_key=root_key,
        key_id=key_id,
        revision=revision,
        salt=_b64(salt),
        nonce=_b64(nonce),
    )
    key = derive(respond(challenge(key_id)), salt, root_key, key_id)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, canonical_header(header))
    return canonical_header(dict(header, ciphertext=_b64(ciphertext)))


def unwrap(encoded, key_id, root_key, respond):
    header, salt, nonce, ciphertext = parse_record(encoded, key_id, root_key)
    key = derive(respond(challenge(key_id)), salt, root_key, key_id)
    return AESGCM(key).decrypt(nonce, ciphertext, canonical_header(header))
