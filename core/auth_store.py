"""Users, memberships, sessions, and email-verification tokens.

All auth state lives in the main SQLite database. Tokens are stored only as
SHA-256 hashes; raw session and verification tokens never touch the database.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from core.state import connect, now_iso


SESSION_TTL_DAYS = 30
VERIFICATION_TTL_HOURS = 24
_initialized: set[str] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def init_auth_db() -> None:
    from core.state import DB_PATH

    key = str(DB_PATH)
    if key in _initialized:
        return
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email_verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS org_memberships (
                org_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'owner',
                created_at TEXT NOT NULL,
                PRIMARY KEY (org_id, user_id),
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                org_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(org_id) REFERENCES buffer_orgs(id)
            );

            CREATE TABLE IF NOT EXISTS email_verifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS auth_sessions_user
            ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS email_verifications_user
            ON email_verifications(user_id);
            """
        )
    _initialized.add(key)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def create_user(email: str, password_hash: str) -> dict[str, Any]:
    init_auth_db()
    email = normalize_email(email)
    timestamp = now_iso()
    user_id = new_id("usr")
    with connect() as db:
        db.execute(
            "INSERT INTO users (id, email, password_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, email, password_hash, timestamp, timestamp),
        )
    return get_user(user_id) or {}


def get_user(user_id: str) -> dict[str, Any] | None:
    init_auth_db()
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    init_auth_db()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM users WHERE email = ?", (normalize_email(email),)
        ).fetchone()
    return dict(row) if row else None


def delete_user(user_id: str) -> None:
    init_auth_db()
    with connect() as db:
        db.execute("DELETE FROM email_verifications WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM org_memberships WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))


def mark_email_verified(user_id: str) -> dict[str, Any] | None:
    init_auth_db()
    timestamp = now_iso()
    with connect() as db:
        db.execute(
            "UPDATE users SET email_verified_at = ?, updated_at = ? WHERE id = ?",
            (timestamp, timestamp, user_id),
        )
    return get_user(user_id)


def add_membership(org_id: int, user_id: str, role: str = "owner") -> None:
    init_auth_db()
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO org_memberships (org_id, user_id, role, created_at) "
            "VALUES (?, ?, ?, ?)",
            (int(org_id), user_id, role, now_iso()),
        )


def memberships_for_user(user_id: str) -> list[dict[str, Any]]:
    init_auth_db()
    with connect() as db:
        rows = db.execute(
            "SELECT m.org_id, m.role, o.name, o.slug, o.plan "
            "FROM org_memberships m JOIN buffer_orgs o ON o.id = m.org_id "
            "WHERE m.user_id = ? ORDER BY m.created_at ASC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def primary_org_for_user(user_id: str) -> dict[str, Any] | None:
    memberships = memberships_for_user(user_id)
    return memberships[0] if memberships else None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str, org_id: int) -> tuple[str, dict[str, Any]]:
    init_auth_db()
    token = secrets.token_urlsafe(32)
    timestamp = _now()
    expires = timestamp + timedelta(days=SESSION_TTL_DAYS)
    session_id = new_id("ses")
    with connect() as db:
        db.execute(
            "INSERT INTO auth_sessions "
            "(id, user_id, org_id, token_hash, created_at, expires_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                user_id,
                int(org_id),
                token_hash(token),
                _iso(timestamp),
                _iso(expires),
                _iso(timestamp),
            ),
        )
    return token, {
        "id": session_id,
        "user_id": user_id,
        "org_id": int(org_id),
        "expires_at": _iso(expires),
    }


def get_session(token: str) -> dict[str, Any] | None:
    init_auth_db()
    digest = token_hash(token)
    with connect() as db:
        row = db.execute(
            "SELECT * FROM auth_sessions WHERE token_hash = ?", (digest,)
        ).fetchone()
        if not row:
            return None
        expires = row["expires_at"]
        try:
            expired = datetime.fromisoformat(expires) <= _now()
        except ValueError:
            expired = True
        if expired:
            db.execute("DELETE FROM auth_sessions WHERE id = ?", (row["id"],))
            return None
        try:
            stale = (_now() - datetime.fromisoformat(row["last_seen_at"])).total_seconds() > 300
        except (ValueError, TypeError):
            stale = True
        if stale:
            db.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
                (_iso(_now()), row["id"]),
            )
        return dict(row)


def delete_session(token: str) -> None:
    init_auth_db()
    with connect() as db:
        db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash(token),))


def create_verification(user_id: str) -> str:
    init_auth_db()
    token = secrets.token_urlsafe(32)
    timestamp = _now()
    with connect() as db:
        db.execute(
            "UPDATE email_verifications SET used_at = ? "
            "WHERE user_id = ? AND used_at IS NULL",
            (_iso(timestamp), user_id),
        )
        db.execute(
            "INSERT INTO email_verifications "
            "(id, user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (
                new_id("ver"),
                user_id,
                token_hash(token),
                _iso(timestamp),
                _iso(timestamp + timedelta(hours=VERIFICATION_TTL_HOURS)),
            ),
        )
    return token


def consume_verification(token: str) -> str | None:
    init_auth_db()
    digest = token_hash(token)
    timestamp = _now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id, user_id, expires_at, used_at FROM email_verifications "
            "WHERE token_hash = ?",
            (digest,),
        ).fetchone()
        if not row or row["used_at"]:
            return None
        try:
            expired = datetime.fromisoformat(row["expires_at"]) <= timestamp
        except ValueError:
            expired = True
        if expired:
            return None
        db.execute(
            "UPDATE email_verifications SET used_at = ? WHERE id = ?",
            (_iso(timestamp), row["id"]),
        )
    return str(row["user_id"])
