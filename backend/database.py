"""
LumiVeil — Database Layer
=========================
SQLite via Python's built-in sqlite3.
No ORM — keeps dependencies minimal and the code readable.

Tables
------
  users   — accounts, tiers, hashed passwords
  usage   — daily analysis counts per user
  payments — payment records (for future Stripe/Razorpay integration)

Usage
-----
  from database import init_db, get_db
  init_db()          # call once at startup
  db = get_db()      # get a connection anywhere
"""

import sqlite3
import os
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), 'lumiveil.db')

SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    tier          TEXT    NOT NULL DEFAULT 'free',  -- 'free' | 'pro' | 'max'
    created_at    TEXT    NOT NULL,
    last_login    TEXT
);

-- Daily usage tracking
CREATE TABLE IF NOT EXISTS usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    date       TEXT    NOT NULL,   -- YYYY-MM-DD
    count      INTEGER NOT NULL DEFAULT 0,
    last_used  TEXT,               -- ISO timestamp of last analysis
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, date)          -- one row per user per day
);

-- Payment records (populated when Stripe/Razorpay webhooks fire)
CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    amount       REAL    NOT NULL,
    currency     TEXT    NOT NULL DEFAULT 'USD',
    provider     TEXT    NOT NULL,   -- 'stripe' | 'razorpay'
    provider_id  TEXT,               -- provider's transaction ID
    tier         TEXT    NOT NULL,   -- tier this payment unlocks
    status       TEXT    NOT NULL DEFAULT 'pending',  -- 'pending' | 'completed' | 'failed'
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

# ---------------------------------------------------------------------------
# Tier limits — single source of truth
# ---------------------------------------------------------------------------
TIER_LIMITS = {
    'free': {
        'daily_limit':      30,
        'refresh_hours':    5,
        'image_analysis':   False,
        'history_limit':    0,
        'api_access':       False,
    },
    'pro': {
        'daily_limit':      300,
        'refresh_hours':    0,      # no wait
        'image_analysis':   True,
        'history_limit':    50,
        'api_access':       False,
    },
    'max': {
        'daily_limit':      999999, # effectively unlimited
        'refresh_hours':    0,
        'image_analysis':   True,
        'history_limit':    999999,
        'api_access':       True,
    },
}


def get_db():
    """Return a sqlite3 connection with row_factory set to Row (dict-like access)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrent read performance
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f'[DB] Initialised at {DB_PATH}')


# ---------------------------------------------------------------------------
# USER HELPERS
# ---------------------------------------------------------------------------

def create_user(email, password_hash):
    """Insert a new user. Returns the new user's id, or None if email taken."""
    try:
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, tier, created_at) VALUES (?, ?, 'free', ?)",
            (email.lower().strip(), password_hash, datetime.utcnow().isoformat())
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        return None   # email already taken


def get_user_by_email(email):
    """Return a user row by email, or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Return a user row by id, or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_last_login(user_id):
    conn = get_db()
    conn.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def set_user_tier(user_id, tier):
    """Upgrade or downgrade a user's tier. Called by payment webhook."""
    if tier not in TIER_LIMITS:
        raise ValueError(f'Unknown tier: {tier}')
    conn = get_db()
    conn.execute("UPDATE users SET tier = ? WHERE id = ?", (tier, user_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# USAGE HELPERS
# ---------------------------------------------------------------------------

def get_usage_today(user_id):
    """
    Return (count, last_used) for today.
    If no row exists yet, returns (0, None).
    """
    today = date.today().isoformat()
    conn  = get_db()
    row   = conn.execute(
        "SELECT count, last_used FROM usage WHERE user_id = ? AND date = ?",
        (user_id, today)
    ).fetchone()
    conn.close()
    if row:
        return row['count'], row['last_used']
    return 0, None


def increment_usage(user_id):
    """
    Increment today's analysis count for a user.
    Uses INSERT OR REPLACE to handle first-use-of-day automatically.
    """
    today = date.today().isoformat()
    now   = datetime.utcnow().isoformat()
    conn  = get_db()
    conn.execute("""
        INSERT INTO usage (user_id, date, count, last_used)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(user_id, date)
        DO UPDATE SET count = count + 1, last_used = excluded.last_used
    """, (user_id, today, now))
    conn.commit()
    conn.close()


def check_usage_allowed(user_id, tier):
    """
    Check whether this user can perform another analysis right now.
    Returns (allowed: bool, reason: str, remaining: int).
    """
    from datetime import datetime, timedelta

    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    daily_limit   = limits['daily_limit']
    refresh_hours = limits['refresh_hours']

    count, last_used = get_usage_today(user_id)

    if count < daily_limit:
        return True, 'ok', daily_limit - count

    # Limit hit — check if refresh window has passed (free tier only)
    if refresh_hours > 0 and last_used:
        last_dt    = datetime.fromisoformat(last_used)
        next_reset = last_dt + timedelta(hours=refresh_hours)
        if datetime.utcnow() >= next_reset:
            # Reset their count for today
            today = date.today().isoformat()
            conn  = get_db()
            conn.execute(
                "UPDATE usage SET count = 0 WHERE user_id = ? AND date = ?",
                (user_id, today)
            )
            conn.commit()
            conn.close()
            return True, 'ok', daily_limit

        wait_mins = int((next_reset - datetime.utcnow()).total_seconds() / 60)
        return False, f'Daily limit reached. Refresh in {wait_mins} minutes.', 0

    return False, f'Daily limit of {daily_limit} analyses reached. Upgrade to Pro for more.', 0


# ---------------------------------------------------------------------------
# PAYMENT HELPERS
# ---------------------------------------------------------------------------

def record_payment(user_id, amount, currency, provider, provider_id, tier):
    """Insert a payment record. Call this from Stripe/Razorpay webhook handler."""
    conn = get_db()
    conn.execute("""
        INSERT INTO payments (user_id, amount, currency, provider, provider_id, tier, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)
    """, (user_id, amount, currency, provider, provider_id, tier, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    # Upgrade the user's tier immediately
    set_user_tier(user_id, tier)
