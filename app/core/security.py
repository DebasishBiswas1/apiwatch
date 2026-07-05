"""
security.py — password hashing and JWT logic.

Why is this its own file?
  These are pure utility functions with no FastAPI or SQLAlchemy
  dependencies. Keeping them isolated makes them easy to test
  independently and easy to swap out (e.g. change hashing algorithm)
  without touching routes or models.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt.

    bcrypt.hashpw requires bytes, not str — we encode first.
    bcrypt.gensalt() generates a random salt and embeds it in the hash,
    so every call produces a different hash even for the same password.
    The result is decoded back to str for storage in the VARCHAR column.

    The returned string looks like:
    "$2b$12$saltsaltsaltsalt...hashhashhashhash"
      ^^ ^^ ^^^^^^^^^^^^^^^^^^
      |  |  random salt (22 chars)
      |  cost factor (12 = 2^12 rounds, ~250ms on modern hardware)
      bcrypt version
    """
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    bcrypt.checkpw extracts the salt from the stored hash, re-hashes
    the input with that same salt, and compares the results.
    Returns True if they match, False otherwise.

    This is timing-safe — bcrypt.checkpw runs in constant time
    regardless of where the comparison fails, preventing timing attacks.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(subject: dict[str, Any]) -> str:
    """
    Create a signed JWT containing the given subject claims.

    subject: a dict of claims to embed — we pass {"user_id": ..., "org_id": ...}
    "sub" is the standard JWT claim for "subject" (who this token is about).
    "exp" is the standard claim for expiry — jose reads this automatically
         on decode and raises JWTError if the token has expired.

    datetime.now(timezone.utc) — always use timezone-aware UTC for JWT
    expiry. Naive datetimes (without timezone) cause subtle bugs when
    servers are in different timezones.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {**subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT. Raises JWTError if invalid or expired.

    jwt.decode does three things automatically:
      1. Verifies the signature using SECRET_KEY
      2. Checks the "exp" claim — raises ExpiredSignatureError if past
      3. Returns the payload dict if everything checks out

    We do not catch JWTError here — we let it propagate to the caller
    (get_current_user) which converts it to an HTTP 401 response.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
