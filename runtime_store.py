import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import ALLOWED_PLATFORMS, DATA_DIR, DEFAULT_MAX_FILE_SIZE_MB
from plans import PERIOD_LABELS, get_plan, get_plan_rule

SETTINGS_FILE = DATA_DIR / "settings.json"
LOGS_DB = DATA_DIR / "activity.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _period_start(period: str, now: datetime | None = None) -> datetime:
    current = now or _utc_datetime()
    base = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return base
    if period == "week":
        return base - timedelta(days=base.weekday())
    if period == "month":
        return base.replace(day=1)
    raise ValueError(f"Unsupported period: {period}")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


from config import COBALT_API_URL, USE_COBALT_API, RAPIDAPI_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
def default_settings() -> dict[str, Any]:
    return {
        "max_file_size_mb": DEFAULT_MAX_FILE_SIZE_MB,
        "downloads_enabled": True,
        "allowed_platforms": ALLOWED_PLATFORMS,
        "use_cobalt_api": USE_COBALT_API,
        "cobalt_api_url": COBALT_API_URL,
        "rapidapi_key": RAPIDAPI_KEY,
        "stripe_secret_key": STRIPE_SECRET_KEY,
        "stripe_webhook_secret": STRIPE_WEBHOOK_SECRET,
        "updated_at": _utc_now(),
    }


def load_settings() -> dict[str, Any]:
    ensure_data_dir()
    if not SETTINGS_FILE.exists():
        settings = default_settings()
        save_settings(settings)
        return settings

    with SETTINGS_FILE.open("r", encoding="utf-8") as f:
        settings = json.load(f)

    merged = default_settings()
    merged.update(settings)
    return merged


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dir()
    normalized = default_settings()
    normalized.update(settings)
    normalized["max_file_size_mb"] = int(normalized["max_file_size_mb"])
    normalized["downloads_enabled"] = bool(normalized["downloads_enabled"])
    normalized["allowed_platforms"] = [
        platform for platform in normalized["allowed_platforms"] if platform in ALLOWED_PLATFORMS
    ]
    normalized["updated_at"] = _utc_now()
    normalized["use_cobalt_api"] = bool(normalized.get("use_cobalt_api", True))
    normalized["cobalt_api_url"] = str(normalized.get("cobalt_api_url", ""))
    normalized["rapidapi_key"] = str(normalized.get("rapidapi_key", ""))
    normalized["stripe_secret_key"] = str(normalized.get("stripe_secret_key", ""))
    normalized["stripe_webhook_secret"] = str(normalized.get("stripe_webhook_secret", ""))

    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    return normalized


def get_max_file_size_bytes() -> int:
    return int(load_settings()["max_file_size_mb"]) * 1024 * 1024


def init_logs_db() -> None:
    ensure_data_dir()
    with sqlite3.connect(LOGS_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                platform TEXT,
                url TEXT,
                metadata TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                plan_code TEXT NOT NULL DEFAULT 'free',
                plan_started_at TEXT,
                plan_expires_at TEXT,
                assigned_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                plan_code TEXT NOT NULL,
                platform TEXT NOT NULL,
                url TEXT,
                media_kind TEXT,
                quality TEXT,
                duration_seconds INTEGER,
                metadata TEXT,
                FOREIGN KEY (telegram_user_id) REFERENCES bot_users (telegram_user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_user_platform_created
            ON usage_events (telegram_user_id, platform, created_at)
            """
        )
        try:
            conn.execute("ALTER TABLE bot_users ADD COLUMN language_code TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()


def add_log(
    level: str,
    event_type: str,
    message: str,
    *,
    platform: str | None = None,
    url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    init_logs_db()
    serialized_metadata = json.dumps(metadata, ensure_ascii=False) if metadata else None
    with sqlite3.connect(LOGS_DB) as conn:
        conn.execute(
            """
            INSERT INTO activity_logs (
                created_at, level, event_type, message, platform, url, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_utc_now(), level.upper(), event_type, message, platform, url, serialized_metadata),
        )
        conn.commit()



def get_dashboard_stats() -> dict[str, int]:
    init_logs_db()
    now = _utc_now()
    with closing(sqlite3.connect(LOGS_DB)) as conn:
        users = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        paid_users = conn.execute("SELECT COUNT(*) FROM bot_users WHERE plan_code != 'free' AND (plan_expires_at IS NULL OR plan_expires_at > ?)", (now,)).fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
        errors = conn.execute("SELECT COUNT(*) FROM activity_logs WHERE level = 'ERROR'").fetchone()[0]
    return {
        "users": users,
        "paid_users": paid_users,
        "total_logs": logs,
        "errors": errors
    }


def list_logs(limit: int = 200) -> list[dict[str, Any]]:
    init_logs_db()
    with closing(sqlite3.connect(LOGS_DB)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, created_at, level, event_type, message, platform, url, metadata
            FROM activity_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else None
        result.append(item)
    return result


def list_user_logs(telegram_user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    logs = list_logs(limit=1000)
    user_logs = []
    for log in logs:
        metadata = log.get("metadata") or {}
        if metadata.get("telegram_user_id") == telegram_user_id:
            user_logs.append(log)
        if len(user_logs) >= limit:
            break
    return user_logs


def upsert_bot_user(
    telegram_user_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
) -> None:
    init_logs_db()
    now = _utc_now()
    with sqlite3.connect(LOGS_DB) as conn:
        conn.execute(
            """
            INSERT INTO bot_users (
                telegram_user_id, username, first_name, last_name, language_code, plan_code,
                plan_started_at, plan_expires_at, assigned_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'free', ?, NULL, NULL, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = COALESCE(excluded.username, bot_users.username),
                first_name = COALESCE(excluded.first_name, bot_users.first_name),
                last_name = COALESCE(excluded.last_name, bot_users.last_name),
                language_code = COALESCE(excluded.language_code, bot_users.language_code),
                updated_at = excluded.updated_at
            """,
            (
                telegram_user_id,
                username or None,
                first_name or None,
                last_name or None,
                language_code or None,
                now,
                now,
                now,
            ),
        )
        conn.commit()


def _row_to_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    user = dict(row)
    expires_at = _parse_datetime(user.get("plan_expires_at"))
    user["is_subscription_active"] = user["plan_code"] == "free" or expires_at is None or expires_at > _utc_datetime()
    user["effective_plan_code"] = user["plan_code"] if user["is_subscription_active"] else "free"
    user["effective_plan"] = get_plan(user["effective_plan_code"])
    user["assigned_plan"] = get_plan(user["plan_code"])
    return user


def get_bot_user(telegram_user_id: int) -> dict[str, Any]:
    init_logs_db()
    with closing(sqlite3.connect(LOGS_DB)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT telegram_user_id, username, first_name, last_name, language_code, plan_code,
                   plan_started_at, plan_expires_at, assigned_note, created_at, updated_at
            FROM bot_users
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        ).fetchone()
    if row is None:
        upsert_bot_user(telegram_user_id)
        return get_bot_user(telegram_user_id)
    return _row_to_user(row) or {}


def assign_user_plan(
    telegram_user_id: int,
    plan_code: str,
    *,
    months: int = 1,
    note: str | None = None,
) -> dict[str, Any]:
    init_logs_db()
    upsert_bot_user(telegram_user_id)
    normalized_plan_code = get_plan(plan_code)["code"]
    now = _utc_datetime()
    expires_at = None if normalized_plan_code == "free" else (now + timedelta(days=max(months, 1) * 30)).isoformat()
    with sqlite3.connect(LOGS_DB) as conn:
        conn.execute(
            """
            UPDATE bot_users
            SET plan_code = ?, plan_started_at = ?, plan_expires_at = ?, assigned_note = ?, updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (
                normalized_plan_code,
                now.isoformat(),
                expires_at,
                note or None,
                now.isoformat(),
                telegram_user_id,
            ),
        )
        conn.commit()
    return get_bot_user(telegram_user_id)


def list_bot_users(limit: int = 200) -> list[dict[str, Any]]:
    init_logs_db()
    with closing(sqlite3.connect(LOGS_DB)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT telegram_user_id, username, first_name, last_name, language_code, plan_code,
                   plan_started_at, plan_expires_at, assigned_note, created_at, updated_at
            FROM bot_users
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    users: list[dict[str, Any]] = []
    for row in rows:
        user = _row_to_user(row)
        if user is not None:
            users.append(user)
    return users


def record_usage_event(
    telegram_user_id: int,
    *,
    platform: str,
    url: str | None = None,
    media_kind: str | None = None,
    quality: str | None = None,
    duration_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    init_logs_db()
    user = get_bot_user(telegram_user_id)
    serialized_metadata = json.dumps(metadata, ensure_ascii=False) if metadata else None
    with sqlite3.connect(LOGS_DB) as conn:
        conn.execute(
            """
            INSERT INTO usage_events (
                telegram_user_id, created_at, plan_code, platform, url,
                media_kind, quality, duration_seconds, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                _utc_now(),
                user["effective_plan_code"],
                platform,
                url,
                media_kind,
                quality,
                duration_seconds,
                serialized_metadata,
            ),
        )
        conn.commit()


def count_usage_events(
    telegram_user_id: int,
    *,
    platform: str,
    period: str,
) -> int:
    init_logs_db()
    period_from = _period_start(period).isoformat()
    with closing(sqlite3.connect(LOGS_DB)) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM usage_events
            WHERE telegram_user_id = ? AND platform = ? AND created_at >= ?
            """,
            (telegram_user_id, platform, period_from),
        ).fetchone()
    return int(row[0] if row else 0)


def get_usage_snapshot(telegram_user_id: int) -> dict[str, Any]:
    user = get_bot_user(telegram_user_id)
    plan = user["effective_plan"]
    usage_rules = []
    for rule in plan["rules"]:
        used = None
        remaining = None
        if rule["limit"] is not None and rule["period"]:
            used = count_usage_events(
                telegram_user_id,
                platform=rule["platform"],
                period=rule["period"],
            )
            remaining = max(rule["limit"] - used, 0)
        usage_rules.append(
            {
                **rule,
                "used": used,
                "remaining": remaining,
                "period_label": PERIOD_LABELS.get(rule["period"]) if rule["period"] else None,
            }
        )
    return {
        "user": user,
        "plan": plan,
        "rules": usage_rules,
    }


def evaluate_download_access(
    telegram_user_id: int,
    *,
    platform: str,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    snapshot = get_usage_snapshot(telegram_user_id)
    plan = snapshot["plan"]
    rule = get_plan_rule(plan["code"], platform)
    if not rule:
        return {
            "allowed": False,
            "reason": f"{platform} در {plan['name']} فعال نیست.",
            "snapshot": snapshot,
            "rule": None,
        }

    max_duration = rule.get("max_duration_seconds")
    if max_duration and duration_seconds and duration_seconds > max_duration:
        return {
            "allowed": False,
            "reason": f"در {plan['name']}، ویدئوهای {platform} باید زیر {max_duration // 60} دقیقه باشند.",
            "snapshot": snapshot,
            "rule": rule,
        }

    if rule["limit"] is None:
        return {
            "allowed": True,
            "reason": None,
            "snapshot": snapshot,
            "rule": rule,
        }

    used = count_usage_events(
        telegram_user_id,
        platform=platform,
        period=rule["period"],
    )
    if used >= rule["limit"]:
        return {
            "allowed": False,
            "reason": f"سهمیه {platform} شما در {PERIOD_LABELS[rule['period']]} جاری تمام شده است ({used}/{rule['limit']}).",
            "snapshot": snapshot,
            "rule": rule,
        }

    return {
        "allowed": True,
        "reason": None,
        "snapshot": snapshot,
        "rule": rule,
        "used": used,
        "remaining": rule["limit"] - used,
    }
