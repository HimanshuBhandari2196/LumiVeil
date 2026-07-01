"""
LumiVeil — Auth Layer
=====================
Handles password hashing and JWT token generation/validation.

Token strategy (Google-style silent refresh)
----------------------------------------------
  - ACCESS token:  short-lived (1 hour). Sent with every /analyze request.
  - REFRESH token: long-lived (60 days). Stored hashed in the database.
                   Used only to silently mint a new access token when the
                   old one expires — the user never has to log in again
                   unless the refresh token itself expires or is revoked.

  Both are signed with HS256 using JWT_SECRET from .env.
"""

import hashlib
import hmac
import base64
import json
import os
import time
import secrets
from database import get_user_by_id, store_refresh_token, get_refresh_token, revoke_refresh_token

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-this-jwt-secret-in-your-env')

ACCESS_TOKEN_LIFETIME_SECONDS  = 60 * 60                 # 1 hour
REFRESH_TOKEN_LIFETIME_SECONDS = 60 * 24 * 60 * 60        # 60 days


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


def generate_access_token(user_id, email, tier):
    """
    Create a short-lived signed JWT access token (1 hour).
    This is what gets sent with every /analyze request.
    """
    return _sign_jwt({
        'user_id': user_id,
        'email':   email,
        'tier':    tier,
        'type':    'access',
        'exp':     int(time.time()) + ACCESS_TOKEN_LIFETIME_SECONDS
    })


# Backward-compatible alias — existing code/extensions calling generate_token()
# keep working and get an access token (old behaviour was effectively this).
def generate_token(user_id, email, tier):
    return generate_access_token(user_id, email, tier)


def _sign_jwt(payload_dict):
    """Internal: encode + sign a JWT payload dict. Returns the token string."""
    header  = _b64encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    payload = _b64encode(json.dumps(payload_dict).encode())

    signing_input = f'{header}.{payload}'
    signature     = _b64encode(
        hmac.new(
            JWT_SECRET.encode(),
            signing_input.encode(),
            hashlib.sha256
        ).digest()
    )
    return f'{signing_input}.{signature}'


def _hash_refresh_token(token):
    """Refresh tokens are stored hashed in the DB — never plaintext."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_refresh_token(user_id):
    """
    Create a long-lived (60-day) opaque refresh token, store its hash in the
    database, and return the plaintext token to send to the client.
    The plaintext is shown only once — only the hash is ever persisted.
    """
    raw_token  = secrets.token_urlsafe(48)
    token_hash = _hash_refresh_token(raw_token)
    expires_at = time.time() + REFRESH_TOKEN_LIFETIME_SECONDS

    from datetime import datetime
    store_refresh_token(
        user_id,
        token_hash,
        datetime.utcfromtimestamp(expires_at).isoformat()
    )
    return raw_token


def issue_token_pair(user_id, email, tier):
    """Convenience: generate both an access token and a refresh token at once."""
    return {
        'access_token':  generate_access_token(user_id, email, tier),
        'refresh_token': generate_refresh_token(user_id),
    }


def refresh_access_token(refresh_token_plaintext):
    """
    Exchange a valid, non-revoked, non-expired refresh token for a brand new
    access token. Returns the new access token string, or raises ValueError.
    """
    from datetime import datetime

    token_hash = _hash_refresh_token(refresh_token_plaintext)
    record     = get_refresh_token(token_hash)

    if not record:
        raise ValueError('Refresh token not recognised')
    if record['revoked']:
        raise ValueError('Refresh token has been revoked — please sign in again')

    expires_at = datetime.fromisoformat(record['expires_at'])
    if datetime.utcnow() >= expires_at:
        raise ValueError('Refresh token has expired — please sign in again')

    user = get_user_by_id(record['user_id'])
    if not user:
        raise ValueError('User no longer exists')

    return generate_access_token(user['id'], user['email'], user['tier'])


def revoke_refresh_token_plaintext(refresh_token_plaintext):
    """Sign-out helper: revoke a refresh token given its plaintext value."""
    revoke_refresh_token(_hash_refresh_token(refresh_token_plaintext))


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
