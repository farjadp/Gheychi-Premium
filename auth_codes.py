"""
کدهای یک‌بارمصرف (one-time codes).

هم ورود با ایمیل و هم اتصال اکانت تلگرام به کد نیاز دارند. اگر هر کدام قوانین
خودش را داشته باشد، دیر یا زود یکی‌شان TTL یا سقف تلاش را کم می‌آورد. پس همه از
اینجا رد می‌شوند.

کدها هرگز خام ذخیره نمی‌شوند. یک کد شش‌رقمی فقط ۱۰^۶ حالت دارد، پس هش ساده در
صورت نشت دیتابیس ظرف چند ثانیه آفلاین شکسته می‌شود؛ HMAC با کلید سرور یعنی
مهاجم بدون آن کلید هیچ کاری نمی‌تواند بکند.
"""
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from contextlib import closing
from datetime import timedelta
from typing import Any

from config import FLASK_SECRET_KEY
from runtime_store import _connect, _utc_datetime, _utc_now, init_logs_db

PURPOSE_EMAIL_LOGIN = "email_login"
PURPOSE_LINK_DEEP = "telegram_link_deep"
PURPOSE_LINK_CODE = "telegram_link_code"

DEFAULT_TTL_SECONDS = 300
MAX_ATTEMPTS = 5


class CodeError(Exception):
    code = "code_failed"


class CodeInvalid(CodeError):
    code = "invalid"


class CodeExpired(CodeError):
    code = "expired"


class CodeExhausted(CodeError):
    """Too many wrong guesses — the code is dead even if the next guess is right."""

    code = "exhausted"


def _hash(code: str) -> str:
    return hmac.new(FLASK_SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_numeric_code(length: int = 6) -> str:
    # secrets, not random: these guard account access.
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_token() -> str:
    # Rides in a Telegram deep link, whose start payload caps at 64 characters.
    return secrets.token_urlsafe(24)


def issue_code(
    purpose: str,
    subject: str,
    *,
    code: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """
    Mint a code and return it in the clear — the caller sends it, then forgets it.

    Any code still outstanding for the same purpose and subject is consumed
    first, so asking for a second code invalidates the first. Otherwise every
    resend would widen the window instead of restarting it.
    """
    init_logs_db()
    value = code or generate_numeric_code()
    now = _utc_datetime()
    with _connect() as conn:
        conn.execute(
            "UPDATE auth_codes SET consumed_at = ? WHERE purpose = ? AND subject = ? AND consumed_at IS NULL",
            (_utc_now(), purpose, subject),
        )
        conn.execute(
            """
            INSERT INTO auth_codes (code_id, purpose, subject, code_hash, created_at, expires_at, attempts)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                uuid.uuid4().hex,
                purpose,
                subject,
                _hash(value),
                now.isoformat(),
                (now + timedelta(seconds=ttl_seconds)).isoformat(),
            ),
        )
        conn.commit()
    return value


def verify_code(purpose: str, subject: str, code: str) -> None:
    """
    Burn the code, or raise why it cannot be burnt.

    Raises CodeInvalid, CodeExpired or CodeExhausted. Returns None on success.
    """
    init_logs_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM auth_codes
            WHERE purpose = ? AND subject = ? AND consumed_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (purpose, subject),
        ).fetchone()
        if row is None:
            raise CodeInvalid("no outstanding code")
        if row["expires_at"] <= _utc_now():
            raise CodeExpired("code expired")
        if row["attempts"] >= MAX_ATTEMPTS:
            raise CodeExhausted("too many attempts")

        if not hmac.compare_digest(row["code_hash"], _hash(code)):
            conn.execute(
                "UPDATE auth_codes SET attempts = attempts + 1 WHERE code_id = ?", (row["code_id"],)
            )
            conn.commit()
            raise CodeInvalid("wrong code")

        conn.execute(
            "UPDATE auth_codes SET consumed_at = ? WHERE code_id = ?", (_utc_now(), row["code_id"])
        )
        conn.commit()


def resolve_token(purpose: str, token: str) -> str | None:
    """
    Look a token up by its value and burn it, returning the subject.

    Deep links carry no subject in the URL — the token *is* the lookup key — so
    this searches by hash instead of by subject.
    """
    init_logs_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM auth_codes
            WHERE purpose = ? AND code_hash = ? AND consumed_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (purpose, _hash(token)),
        ).fetchone()
        if row is None or row["expires_at"] <= _utc_now():
            return None
        conn.execute(
            "UPDATE auth_codes SET consumed_at = ? WHERE code_id = ?", (_utc_now(), row["code_id"])
        )
        conn.commit()
        return row["subject"]


def purge_expired(older_than_days: int = 7) -> int:
    """Housekeeping so the table does not grow without bound."""
    init_logs_db()
    cutoff = (_utc_datetime() - timedelta(days=older_than_days)).isoformat()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM auth_codes WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
