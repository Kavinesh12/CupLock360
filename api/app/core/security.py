import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_ph = PasswordHasher()  # Argon2id with library defaults


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tv": token_version,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def otp_hash(challenge_id: str, code: str) -> str:
    """Keyed hash binding the code to its challenge; the plain code is never stored."""
    key = get_settings().otp_secret.encode()
    return hmac.new(key, f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
