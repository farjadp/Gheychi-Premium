"""
بخش مالی داشبورد: فاکتورها، ارتقای پلن، و پرداخت.

Stripe از قبل زنده است و پنل ادمین یک webhook کامل برای
checkout.session.completed دارد. این ماژول عمداً همان قرارداد را رعایت می‌کند
— client_reference_id به شکل "<telegram_user_id>_<plan_code>" — تا پرداخت از
وب دقیقاً از همان مسیری فعال شود که پرداخت از بات می‌شود. یک مسیر فعال‌سازی،
نه دو تا که یکی‌شان به‌مرور از دیگری عقب بیفتد.
"""
import logging
from contextlib import closing
from typing import Any

import stripe

from config import STRIPE_SECRET_KEY
from plans import get_plan, list_plans
from runtime_store import _connect, init_logs_db, load_settings

logger = logging.getLogger(__name__)

PLAN_RANK = {"free": 0, "starter": 1, "standard": 2, "pro": 3}


class BillingError(Exception):
    code = "billing_failed"


class StripeNotConfigured(BillingError):
    code = "stripe_not_configured"


class NoTelegramAccount(BillingError):
    """A plan is granted to a Telegram account, so there has to be one."""

    code = "no_telegram_account"


class InvalidPlan(BillingError):
    code = "invalid_plan"


def _stripe_key() -> str:
    # The panel can override the env var, and the bot already prefers settings.
    return load_settings().get("stripe_secret_key") or STRIPE_SECRET_KEY or ""


def is_configured() -> bool:
    return bool(_stripe_key())


def account_invoices(account_id: str) -> list[dict[str, Any]]:
    """
    Every transaction across the Telegram accounts linked here, newest first.

    Invoices follow the account rather than the Telegram account that happened
    to pay, so linking a second device does not hide the receipts.
    """
    init_logs_db()
    with closing(_connect()) as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT telegram_user_id FROM account_telegram_links WHERE account_id = ?", (account_id,)
        ).fetchall()]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""SELECT tx_id, telegram_user_id, amount_usd, payment_method, status,
                       plan_code, created_at
                FROM transactions WHERE telegram_user_id IN ({placeholders})
                ORDER BY created_at DESC""",
            ids,
        ).fetchall()

    invoices = []
    for tx_id, tg, amount, method, status, plan_code, created_at in rows:
        plan = get_plan(plan_code) or {}
        invoices.append({
            "tx_id": tx_id,
            # A Stripe session id is 60-odd characters of noise on a receipt.
            "reference": tx_id[:18] + ("…" if len(tx_id) > 18 else ""),
            "telegram_user_id": tg,
            "amount_usd": amount,
            "payment_method": method,
            "status": status,
            "plan_code": plan_code,
            "plan_name": plan.get("name_en") or plan.get("name") or plan_code,
            "created_at": created_at,
            "is_paid": (status or "").lower() in ("completed", "paid", "succeeded"),
            "is_pending": (status or "").lower() == "pending",
        })
    return invoices


def upgrade_options(current_plan_code: str) -> list[dict[str, Any]]:
    """
    Paid plans, each marked relative to the one in force.

    Downgrades are shown but not offered as a click: with manual activation
    still in the loop, a self-service downgrade is a refund conversation, not a
    button.
    """
    current_rank = PLAN_RANK.get(current_plan_code, 0)
    options = []
    for plan in list_plans():
        code = plan.get("code")
        if not code or plan.get("price_usd", 0) <= 0:
            continue
        rank = PLAN_RANK.get(code, 0)
        options.append({
            "code": code,
            "name": plan.get("name_en") or plan.get("name") or code,
            "price_usd": plan.get("price_usd"),
            "description": plan.get("description_en") or plan.get("description") or "",
            "rules": plan.get("rules", []),
            "max_linked_accounts": plan.get("max_linked_accounts"),
            "is_current": code == current_plan_code,
            "is_upgrade": rank > current_rank,
            "is_downgrade": rank < current_rank,
        })
    return options


def create_checkout_session(
    account_id: str,
    plan_code: str,
    telegram_user_id: int,
    *,
    success_url: str,
    cancel_url: str,
) -> str:
    """
    Start a Stripe Checkout and return the URL to send the buyer to.

    client_reference_id keeps the bot's exact shape so the existing webhook
    activates the plan with no change and no second code path.
    """
    key = _stripe_key()
    if not key:
        raise StripeNotConfigured("Stripe is not configured")
    if not telegram_user_id:
        raise NoTelegramAccount("no Telegram account is linked to this account")

    plan = get_plan(plan_code)
    if not plan or plan.get("price_usd", 0) <= 0:
        raise InvalidPlan(f"{plan_code} is not a purchasable plan")

    stripe.api_key = key
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": plan.get("name_en") or plan.get("name"),
                    "description": f"Gheychi Premium — {plan.get('name_en') or plan.get('name')} monthly subscription",
                },
                "unit_amount": int(plan["price_usd"] * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=f"{telegram_user_id}_{plan_code}",
        metadata={
            "source": "پنل کاربری",
            "telegram_user_id": telegram_user_id,
            "account_id": account_id,
            "plan_code": plan_code,
        },
    )
    return session.url
