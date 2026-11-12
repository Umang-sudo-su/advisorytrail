"""Small authenticated encryption helper for credentials stored in Postgres.

There is no `cryptography` package in this image, so this uses a standard
HMAC-SHA256 keystream (CTR-style) with an HMAC tag. The key is derived from the
app secret, which never leaves the server.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app.auth import SECRET_KEY

_PREFIX = "v1"
_BLOCK = 32


def _keys() -> tuple[bytes, bytes]:
    root = hashlib.sha256(f"advisorytrail-secret-box:{SECRET_KEY}".encode("utf-8")).digest()
    encryption_key = hmac.new(root, b"encryption", hashlib.sha256).digest()
    mac_key = hmac.new(root, b"authentication", hashlib.sha256).digest()
    return encryption_key, mac_key


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def seal(plaintext: str) -> str:
    encryption_key, mac_key = _keys()
    nonce = os.urandom(16)
    data = plaintext.encode("utf-8")
    ciphertext = bytes(a ^ b for a, b in zip(data, _keystream(encryption_key, nonce, len(data))))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return ".".join(
        [
            _PREFIX,
            base64.urlsafe_b64encode(nonce).decode("ascii"),
            base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            base64.urlsafe_b64encode(tag).decode("ascii"),
        ]
    )


def open_sealed(sealed: str) -> str | None:
    try:
        version, nonce_b64, cipher_b64, tag_b64 = sealed.split(".")
        if version != _PREFIX:
            return None
        nonce = base64.urlsafe_b64decode(nonce_b64)
        ciphertext = base64.urlsafe_b64decode(cipher_b64)
        tag = base64.urlsafe_b64decode(tag_b64)
        encryption_key, mac_key = _keys()
        expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, tag):
            return None
        return bytes(a ^ b for a, b in zip(ciphertext, _keystream(encryption_key, nonce, len(ciphertext)))).decode(
            "utf-8"
        )
    except Exception:
        return None
