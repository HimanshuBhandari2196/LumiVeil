"""
LumiVeil — Auth Layer
=====================
Handles password hashing and JWT token generation/validation.

Tokens
------
  - Signed with HS256 using JWT_SECRET from .env
  - Payload: { user_id, email, tier, exp }
  - Expiry:  7 days (refreshed on each login)
"""

import hashlib
import hmac
import base64
import json
import os
import time
from database import get_user_by_id

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-this-jwt-secret-in-your-env')


# ---------------------------------------------------------------------------
# PASSWORD HASHING
# Uses SHA-256 with a secret pepper (LUMIVEIL_API_KEY acts as pepper).
# For production at scale, swap to bcrypt — but SHA-256 is fine for MVP.
# ---------------------------------------------------------------------------

_PEPPER = os.environ.get('LUMIVEIL_API_KEY', 'lumiveil-pepper')


def hash_password(password):
    """Return a hex-encoded SHA-256 hash of password + pepper."""
    return hashlib.sha256(f'{_PEPPER}{password}'.encode()).hexdigest()


def verify_password(password, stored_hash):
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(hash_password(password), stored_hash)


# ---------------------------------------------------------------------------
# MINIMAL JWT (no external library — keeps dependencies lean)
# ---------------------------------------------------------------------------

def _b64encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _b64decode(s):
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + '=' * padding)


def generate_token(user_id, email, tier):
    """
    Create a signed JWT with 7-day expiry.
    Returns a string token.
    """
    header  = _b64encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    payload = _b64encode(json.dumps({
        'user_id': user_id,
        'email':   email,
        'tier':    tier,
        'exp':     int(time.time()) + (7 * 24 * 3600)   # 7 days
    }).encode())

    signing_input = f'{header}.{payload}'
    signature     = _b64encode(
        hmac.new(
            JWT_SECRET.encode(),
            signing_input.encode(),
            hashlib.sha256
        ).digest()
    )
    return f'{signing_input}.{signature}'


def validate_token(token):
    """
    Validate a JWT string.
    Returns the payload dict on success, or raises ValueError with a reason.
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError('Malformed token')

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f'{header_b64}.{payload_b64}'

        expected_sig = _b64encode(
            hmac.new(
                JWT_SECRET.encode(),
                signing_input.encode(),
                hashlib.sha256
            ).digest()
        )

        if not hmac.compare_digest(sig_b64, expected_sig):
            raise ValueError('Invalid token signature')

        payload = json.loads(_b64decode(payload_b64))

        if payload.get('exp', 0) < int(time.time()):
            raise ValueError('Token has expired')

        return payload

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise ValueError(str(e))


def get_user_from_token(token):
    """
    Validate token and return a fresh user dict from the database.
    Returns None if token is invalid or user not found.
    Always fetches from DB so tier changes take effect immediately.
    """
    try:
        payload = validate_token(token)
        user    = get_user_by_id(payload['user_id'])
        return user
    except (ValueError, Exception):
        return None
