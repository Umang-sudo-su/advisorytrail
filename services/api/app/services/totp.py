"""TOTP (RFC 6238) without third-party dependencies.

Secrets are base32, codes are 6 digits on a 30-second step, and verification
accepts one step of clock drift in each direction.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Iterable, List
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
ISSUER = "AdvisoryTrail"


def generate_secret(byte_length: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(byte_length)).decode("ascii").rstrip("=")


def _decode(secret: str) -> bytes:
    padded = secret.upper().strip()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded)


def code_at(secret: str, timestamp: float | None = None, step: int = STEP_SECONDS) -> str:
    counter = int((timestamp if timestamp is not None else time.time()) // step)
    digest = hmac.new(_decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**DIGITS)).zfill(DIGITS)


def verify_code(secret: str, code: str, window: int = 1) -> bool:
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != DIGITS:
        return False

    now = time.time()
    for offset in range(-window, window + 1):
        expected = code_at(secret, now + offset * STEP_SECONDS)
        if hmac.compare_digest(expected, candidate):
            return True
    return False


def provisioning_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def generate_recovery_codes(count: int = 8) -> List[str]:
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    normalised = (code or "").strip().replace("-", "").replace(" ", "").upper()
    return hashlib.sha256(f"recovery:{normalised}".encode("utf-8")).hexdigest()


def hash_recovery_codes(codes: Iterable[str]) -> List[str]:
    return [hash_recovery_code(code) for code in codes]
