from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 240_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2":
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iters)
    )
    return hmac.compare_digest(check.hex(), digest)


def csrf_ok(expected: str, token: str) -> bool:
    if not expected or not token:
        return False
    try:
        return hmac.compare_digest(expected, token)
    except Exception:
        return False


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def random_secret() -> str:
    return secrets.token_urlsafe(48)
