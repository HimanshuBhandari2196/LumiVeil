"""
LumiVeil — Database Layer
=========================
PostgreSQL via psycopg2. Switched from SQLite to persist data
across Railway redeploys (SQLite lives on ephemeral filesystem).

Tables
------
  users          — accounts, tiers, hashed passwords
  usage          — daily analysis counts per user
  payments       — payment records (Stripe/Razorpay)
  refresh_tokens — long-lived tokens for silent re-auth
"""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, date

DATABASE_URL = os.environ.get('DATABASE_URL', '')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    tier          TEXT    NOT NULL DEFAULT 'free',
    created_at    TEXT    NOT NULL,
    last_login    TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0
);

-- Add email_verified column if it doesn't exist (for existing deployments)
DO $$ BEGIN
    ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified INTEGER NOT NULL DEFAULT 0;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS usage (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    date       TEXT    NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    last_used  TEXT,
    UNIQUE(user_id, date)
);

-- Anonymous / guest usage, keyed by a hashed client IP rather than a user
-- account. This is what actually enforces the "30 analyses/day" guest cap
-- shown in the extension UI — it did not exist before, so guests were
-- effectively unlimited once the in-memory rate limiter reset.
CREATE TABLE IF NOT EXISTS guest_usage (
    id         SERIAL PRIMARY KEY,
    ip_hash    TEXT    NOT NULL,
    date       TEXT    NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    last_used  TEXT,
    UNIQUE(ip_hash, date)
);

CREATE TABLE IF NOT EXISTS payments (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    amount       REAL    NOT NULL,
    currency     TEXT    NOT NULL DEFAULT 'USD',
    provider     TEXT    NOT NULL,
    provider_id  TEXT,
    tier         TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending',
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    token_hash  TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS email_verifications (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    token      TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS password_resets (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    token      TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Tier limits — single source of truth
# ---------------------------------------------------------------------------
TIER_LIMITS = {
    'free': {
        'daily_limit':    30,
        'refresh_hours':  5,
        'image_analysis': False,
        'history_limit':  0,
        'api_access':     False,
    },
    'pro': {
        'daily_limit':    300,
        'refresh_hours':  0,
        'image_analysis': True,
        'history_limit':  50,
        'api_access':     False,
    },
    'max': {
        'daily_limit':    999999,
        'refresh_hours':  0,
        'image_analysis': True,
        'history_limit':  999999,
        'api_access':     True,
    },
}


def get_db():
    """Return a psycopg2 connection with RealDictCursor for dict-like row access."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(SCHEMA)
    conn.commit()
    cur.close()
    conn.close()
    print('[DB] PostgreSQL initialised')


# ---------------------------------------------------------------------------
# USER HELPERS
# ---------------------------------------------------------------------------

def create_user(email, password_hash):
    """Insert a new user. Returns the new user's id, or None if email taken."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, tier, created_at) VALUES (%s, %s, 'free', %s) RETURNING id",
            (email.lower().strip(), password_hash, datetime.utcnow().isoformat())
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return user_id
    except psycopg2.IntegrityError:
        return None


def get_user_by_email(email):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def update_last_login(user_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE users SET last_login = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), user_id))
    conn.commit()
    cur.close(); conn.close()


def set_user_tier(user_id, tier):
    if tier not in TIER_LIMITS:
        raise ValueError(f'Unknown tier: {tier}')
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE users SET tier = %s WHERE id = %s", (tier, user_id))
    conn.commit()
    cur.close(); conn.close()


# ---------------------------------------------------------------------------
# USAGE HELPERS
# ---------------------------------------------------------------------------

def get_usage_today(user_id):
    today = date.today().isoformat()
    conn  = get_db()
    cur   = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT count, last_used FROM usage WHERE user_id = %s AND date = %s",
        (user_id, today)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    if row:
        return row['count'], row['last_used']
    return 0, None


def increment_usage(user_id):
    today = date.today().isoformat()
    now   = datetime.utcnow().isoformat()
    conn  = get_db()
    cur   = conn.cursor()
    cur.execute("""
        INSERT INTO usage (user_id, date, count, last_used)
        VALUES (%s, %s, 1, %s)
        ON CONFLICT (user_id, date)
        DO UPDATE SET count = usage.count + 1, last_used = EXCLUDED.last_used
    """, (user_id, today, now))
    conn.commit()
    cur.close(); conn.close()


def check_usage_allowed(user_id, tier):
    from datetime import datetime, timedelta
    limits        = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    daily_limit   = limits['daily_limit']
    refresh_hours = limits['refresh_hours']

    count, last_used = get_usage_today(user_id)

    if count < daily_limit:
        return True, 'ok', daily_limit - count

    if refresh_hours > 0 and last_used:
        last_dt    = datetime.fromisoformat(last_used)
        next_reset = last_dt + timedelta(hours=refresh_hours)
        if datetime.utcnow() >= next_reset:
            today = date.today().isoformat()
            conn  = get_db()
            cur   = conn.cursor()
            cur.execute(
                "UPDATE usage SET count = 0 WHERE user_id = %s AND date = %s",
                (user_id, today)
            )
            conn.commit()
            cur.close(); conn.close()
            return True, 'ok', daily_limit

        wait_mins = int((next_reset - datetime.utcnow()).total_seconds() / 60)
        return False, f'Daily limit reached. Refresh in {wait_mins} minutes.', 0

    return False, f'Daily limit of {daily_limit} analyses reached. Upgrade to Pro for more.', 0


# ---------------------------------------------------------------------------
# GUEST USAGE HELPERS
# ---------------------------------------------------------------------------
# Anonymous requests (no JWT) are identified by a hashed client IP instead
# of a user id. This is the persistent, DB-backed cap that replaces the old
# "no tracking at all" behaviour — it survives server restarts, unlike the
# in-memory Flask-Limiter counters.

GUEST_DAILY_LIMIT = TIER_LIMITS['free']['daily_limit']


def get_guest_usage_today(ip_hash):
    today = date.today().isoformat()
    conn  = get_db()
    cur   = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT count, last_used FROM guest_usage WHERE ip_hash = %s AND date = %s",
        (ip_hash, today)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    if row:
        return row['count'], row['last_used']
    return 0, None


def increment_guest_usage(ip_hash):
    today = date.today().isoformat()
    now   = datetime.utcnow().isoformat()
    conn  = get_db()
    cur   = conn.cursor()
    cur.execute("""
        INSERT INTO guest_usage (ip_hash, date, count, last_used)
        VALUES (%s, %s, 1, %s)
        ON CONFLICT (ip_hash, date)
        DO UPDATE SET count = guest_usage.count + 1, last_used = EXCLUDED.last_used
    """, (ip_hash, today, now))
    conn.commit()
    cur.close(); conn.close()


def check_guest_usage_allowed(ip_hash):
    """
    Guests get a flat daily cap (same number as the free tier) with no
    refresh-window grace period — that's reserved for account holders.
    Returns (allowed: bool, reason: str, remaining: int).
    """
    count, _ = get_guest_usage_today(ip_hash)
    if count < GUEST_DAILY_LIMIT:
        return True, 'ok', GUEST_DAILY_LIMIT - count
    return False, (
        f'Guest daily limit of {GUEST_DAILY_LIMIT} analyses reached. '
        f'Sign up for a free account to keep your own tracked limit.'
    ), 0


# ---------------------------------------------------------------------------
# PAYMENT HELPERS
# ---------------------------------------------------------------------------

def record_payment(user_id, amount, currency, provider, provider_id, tier):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, amount, currency, provider, provider_id, tier, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s)
    """, (user_id, amount, currency, provider, provider_id, tier, datetime.utcnow().isoformat()))
    conn.commit()
    cur.close(); conn.close()
    set_user_tier(user_id, tier)


# ---------------------------------------------------------------------------
# REFRESH TOKEN HELPERS
# ---------------------------------------------------------------------------

def store_refresh_token(user_id, token_hash, expires_at):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO refresh_tokens (user_id, token_hash, created_at, expires_at, revoked)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, token_hash, datetime.utcnow().isoformat(), expires_at))
    conn.commit()
    cur.close(); conn.close()


def get_refresh_token(token_hash):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM refresh_tokens WHERE token_hash = %s", (token_hash,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def revoke_refresh_token(token_hash):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = %s", (token_hash,))
    conn.commit()
    cur.close(); conn.close()


def revoke_all_refresh_tokens(user_id):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close(); conn.close()

# ---------------------------------------------------------------------------
# EMAIL VERIFICATION HELPERS
# ---------------------------------------------------------------------------

def create_email_verification_token(user_id):
    """Create a verification token valid for 24 hours. Returns the raw token."""
    import secrets as _secrets
    from datetime import timedelta
    token      = _secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    conn = get_db()
    cur  = conn.cursor()
    # Invalidate any existing unused tokens for this user first
    cur.execute("UPDATE email_verifications SET used = 1 WHERE user_id = %s AND used = 0", (user_id,))
    cur.execute("""
        INSERT INTO email_verifications (user_id, token, created_at, expires_at, used)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, token, datetime.utcnow().isoformat(), expires_at))
    conn.commit()
    cur.close(); conn.close()
    return token


def verify_email_token(token):
    """
    Validate and consume an email verification token.
    Returns the user_id on success, or None on failure.
    """
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM email_verifications WHERE token = %s AND used = 0", (token,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return None

    # Check expiry
    expires_at = datetime.fromisoformat(row['expires_at'])
    if datetime.utcnow() > expires_at:
        cur.close(); conn.close()
        return None

    # Mark token used and verify user
    cur.execute("UPDATE email_verifications SET used = 1 WHERE id = %s", (row['id'],))
    cur.execute("UPDATE users SET email_verified = 1 WHERE id = %s", (row['user_id'],))
    conn.commit()
    cur.close(); conn.close()
    return row['user_id']


# ---------------------------------------------------------------------------
# PASSWORD RESET HELPERS
# ---------------------------------------------------------------------------

def create_password_reset_token(user_id):
    """Create a password reset token valid for 1 hour. Returns the raw token."""
    import secrets as _secrets
    from datetime import timedelta
    token      = _secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE password_resets SET used = 1 WHERE user_id = %s AND used = 0", (user_id,))
    cur.execute("""
        INSERT INTO password_resets (user_id, token, created_at, expires_at, used)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, token, datetime.utcnow().isoformat(), expires_at))
    conn.commit()
    cur.close(); conn.close()
    return token


def verify_password_reset_token(token):
    """
    Validate a password reset token without consuming it.
    Returns the user_id on success, or None on failure.
    """
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM password_resets WHERE token = %s AND used = 0", (token,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return None
    expires_at = datetime.fromisoformat(row['expires_at'])
    if datetime.utcnow() > expires_at:
        cur.close(); conn.close()
        return None
    cur.close(); conn.close()
    return row['user_id']


def consume_password_reset_token(token, new_password_hash):
    """Consume a reset token and update the user's password."""
    user_id = verify_password_reset_token(token)
    if not user_id:
        return False
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE password_resets SET used = 1 WHERE token = %s", (token,))
    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_password_hash, user_id))
    conn.commit()
    cur.close(); conn.close()
    return True
