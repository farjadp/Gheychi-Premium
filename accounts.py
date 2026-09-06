"""
مدل اکانت کاربر (Account model).

تا پیش از این، هویت کاربر فقط telegram_user_id بود. حالا یک اکانت وب می‌تواند
چند اکانت تلگرام داشته باشد، پس هویت به اینجا منتقل می‌شود.

مدل C: پلن به اکانت تعلق دارد، اما تعداد اکانت‌های تلگرامِ متصل بر اساس تیر
محدود است و یک اسلات آزادشده تا هفت روز قابل استفاده‌ی دوباره نیست. این دو با
هم جلوی تبدیل‌شدن یک اشتراک به اشتراک پنج نفر را می‌گیرند، بدون اینکه کاربری
که واقعاً دو اکانت تلگرام دارد اذیت شود.
"""
import sqlite3
import uuid
from contextlib import closing
from datetime import timedelta
from typing import Any

from plans import get_max_linked_accounts
from runtime_store import _connect, _parse_datetime, _utc_datetime, _utc_now, init_logs_db

UNLINK_COOLDOWN_DAYS = 7


class LinkError(Exception):
    """Base for every refusal to link a Telegram account."""

    code = "link_failed"


class AlreadyLinkedHere(LinkError):
    code = "already_linked_here"


class OwnedByAnotherAccount(LinkError):
    """The Telegram account belongs to someone else's account."""

    code = "owned_by_another"

    def __init__(self, masked_email: str):
        super().__init__(f"already linked to {masked_email}")
        self.masked_email = masked_email


class SlotCapReached(LinkError):
    code = "cap_reached"

    def __init__(self, cap: int):
        super().__init__(f"plan allows {cap} linked Telegram account(s)")
        self.cap = cap


class CooldownActive(LinkError):
    code = "cooldown"

    def __init__(self, reusable_at: str):
        super().__init__(f"slot is on cooldown until {reusable_at}")
        self.reusable_at = reusable_at


def normalise_email(email: str) -> str:
    """
    Lowercased and stripped, so the UNIQUE index does the deduplication and
    'Farjad@Gmail.com' cannot become a second account beside 'farjad@gmail.com'.
    """
    return (email or "").strip().lower()


def mask_email(email: str | None) -> str:
    """
    Enough for the owner to recognise their own address, not enough to hand a
    stranger's address to whoever is trying to link the account.
    """
    if not email:
        return "an account with no email"
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    head = local[0] if local else "*"
    return f"{head}***@{domain}"


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def create_account(email: str | None = None) -> dict[str, Any]:
    """
    Create an account. `email` may be None: a user who arrives through the bot
    gets an account immediately so their links and plan have somewhere to hang,
    and they can attach an email later without anything being migrated.
    """
    init_logs_db()
    account_id = uuid.uuid4().hex
    now = _utc_now()
    stored = normalise_email(email) if email else None
    with _connect() as conn:
        conn.execute(
            "INSERT INTO accounts (account_id, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (account_id, stored, now, now),
        )
        conn.commit()
    return {"account_id": account_id, "email": stored, "created_at": now, "updated_at": now}


def get_account(account_id: str) -> dict[str, Any] | None:
    init_logs_db()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        return _row_to_dict(
            conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        )


def get_account_by_email(email: str) -> dict[str, Any] | None:
    init_logs_db()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        return _row_to_dict(
            conn.execute("SELECT * FROM accounts WHERE email = ?", (normalise_email(email),)).fetchone()
        )


def get_account_by_telegram(telegram_user_id: int) -> dict[str, Any] | None:
    init_logs_db()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        return _row_to_dict(
            conn.execute(
                """
                SELECT a.* FROM accounts a
                JOIN account_telegram_links l ON l.account_id = a.account_id
                WHERE l.telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
        )


def set_account_email(account_id: str, email: str) -> None:
    init_logs_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE accounts SET email = ?, updated_at = ? WHERE account_id = ?",
            (normalise_email(email), _utc_now(), account_id),
        )
        conn.commit()


def list_links(account_id: str) -> list[dict[str, Any]]:
    """Linked Telegram accounts, with whatever profile the bot has recorded."""
    init_logs_db()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT l.telegram_user_id, l.linked_at,
                   u.username, u.first_name, u.last_name, u.plan_code
            FROM account_telegram_links l
            LEFT JOIN bot_users u ON u.telegram_user_id = l.telegram_user_id
            WHERE l.account_id = ?
            ORDER BY l.linked_at
            """,
            (account_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _active_cooldown(conn, account_id: str, telegram_user_id: int) -> str | None:
    row = conn.execute(
        """
        SELECT reusable_at FROM link_cooldowns
        WHERE account_id = ? AND telegram_user_id != ? AND reusable_at > ?
        ORDER BY reusable_at DESC LIMIT 1
        """,
        (account_id, telegram_user_id, _utc_now()),
    ).fetchone()
    return row[0] if row else None


def account_plan_code(account_id: str) -> str:
    """
    The plan this account is entitled to.

    Phase 1 still stores the plan on bot_users, so the account's plan is the
    best one among its linked Telegram accounts. Phase 2 moves the column onto
    accounts and this becomes a plain read.
    """
    order = {"free": 0, "starter": 1, "standard": 2, "pro": 3}
    best = "free"
    for link in list_links(account_id):
        code = link.get("plan_code") or "free"
        if order.get(code, 0) > order.get(best, 0):
            best = code
    return best


def link_telegram(account_id: str, telegram_user_id: int) -> None:
    """
    Attach a Telegram account, or raise the specific reason it cannot be.

    Every refusal is its own exception type because the bot has to explain the
    difference to the user: "you already did this" and "this belongs to someone
    else" call for very different next steps.
    """
    init_logs_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT account_id FROM account_telegram_links WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if existing:
            if existing["account_id"] == account_id:
                raise AlreadyLinkedHere("this Telegram account is already linked here")
            owner = conn.execute(
                "SELECT email FROM accounts WHERE account_id = ?", (existing["account_id"],)
            ).fetchone()
            raise OwnedByAnotherAccount(mask_email(owner["email"] if owner else None))

        cap = get_max_linked_accounts(account_plan_code(account_id))
        used = conn.execute(
            "SELECT COUNT(*) FROM account_telegram_links WHERE account_id = ?", (account_id,)
        ).fetchone()[0]
        if used >= cap:
            raise SlotCapReached(cap)

        cooldown = _active_cooldown(conn, account_id, telegram_user_id)
        if cooldown:
            raise CooldownActive(cooldown)

        conn.execute(
            "INSERT INTO account_telegram_links (telegram_user_id, account_id, linked_at) VALUES (?, ?, ?)",
            (telegram_user_id, account_id, _utc_now()),
        )
        # Relinking the same Telegram account should not be punished, so its own
        # cooldown rows are cleared. Only a *different* account taking the freed
        # slot has to wait, which is what stops a seat being passed around.
        conn.execute(
            "DELETE FROM link_cooldowns WHERE account_id = ? AND telegram_user_id = ?",
            (account_id, telegram_user_id),
        )
        conn.commit()


def unlink_telegram(account_id: str, telegram_user_id: int) -> bool:
    """Detach a Telegram account and start the cooldown on the freed slot."""
    init_logs_db()
    now = _utc_datetime()
    reusable_at = (now + timedelta(days=UNLINK_COOLDOWN_DAYS)).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM account_telegram_links WHERE account_id = ? AND telegram_user_id = ?",
            (account_id, telegram_user_id),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "INSERT INTO link_cooldowns (account_id, telegram_user_id, unlinked_at, reusable_at) VALUES (?, ?, ?, ?)",
            (account_id, telegram_user_id, now.isoformat(), reusable_at),
        )
        conn.commit()
    return True


def link_capacity(account_id: str) -> dict[str, Any]:
    """Slots used and allowed, for the profile page."""
    plan_code = account_plan_code(account_id)
    cap = get_max_linked_accounts(plan_code)
    used = len(list_links(account_id))
    return {"plan_code": plan_code, "used": used, "cap": cap, "remaining": max(cap - used, 0)}
