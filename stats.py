"""
آمار کاربر برای داشبورد.

هدف عددهایی است که کاربر دوست دارد نگاهشان کند: چقدر کار کرده، چه چیزی بیشتر
می‌گیرد، و نسبت به بقیه کجاست.

درباره‌ی مقایسه با دیگران: فقط صدک و میانه برمی‌گردد، هرگز اطلاعات کاربر دیگری.
کاربر می‌فهمد «از ۷۸٪ اعضا فعال‌تری» ولی نمی‌تواند بفهمد آن ۷۸٪ چه کسانی‌اند یا
چه گرفته‌اند.
"""
from contextlib import closing
from datetime import timedelta
from typing import Any

import categories
from runtime_store import _connect, _utc_datetime, _utc_now, init_logs_db

# Below this many active users a percentile is noise dressed up as insight, and
# with a handful of users it can also point at a specific person.
MIN_PEERS_FOR_COMPARISON = 8


def _account_telegram_ids(conn, account_id: str) -> list[int]:
    rows = conn.execute(
        "SELECT telegram_user_id FROM account_telegram_links WHERE account_id = ?", (account_id,)
    ).fetchall()
    return [r[0] for r in rows]


def account_history(account_id: str, limit: int = 500) -> list[dict[str, Any]]:
    """
    Download history across every Telegram account linked here.

    One account, one history — which is the point of the account existing.
    """
    init_logs_db()
    with closing(_connect()) as conn:
        ids = _account_telegram_ids(conn, account_id)
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""
            SELECT id, telegram_user_id, created_at, platform, url, media_kind,
                   quality, duration_seconds
            FROM usage_events
            WHERE telegram_user_id IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*ids, limit),
        ).fetchall()
        cols = ["id", "telegram_user_id", "created_at", "platform", "url", "media_kind", "quality", "duration_seconds"]
    return categories.annotate([dict(zip(cols, r)) for r in rows])


def account_stats(account_id: str) -> dict[str, Any]:
    """Headline numbers plus a peer comparison that discloses nothing about peers."""
    init_logs_db()
    now = _utc_datetime()
    with closing(_connect()) as conn:
        ids = _account_telegram_ids(conn, account_id)
        if not ids:
            return _empty_stats()
        placeholders = ",".join("?" * len(ids))

        total, first_at, seconds = conn.execute(
            f"""SELECT COUNT(*), MIN(created_at), COALESCE(SUM(duration_seconds), 0)
                FROM usage_events WHERE telegram_user_id IN ({placeholders})""",
            ids,
        ).fetchone()

        def since(days):
            cutoff = (now - timedelta(days=days)).isoformat()
            return conn.execute(
                f"SELECT COUNT(*) FROM usage_events WHERE telegram_user_id IN ({placeholders}) AND created_at >= ?",
                (*ids, cutoff),
            ).fetchone()[0]

        last_30, last_7 = since(30), since(7)

        rows = conn.execute(
            f"""SELECT platform, media_kind, quality FROM usage_events
                WHERE telegram_user_id IN ({placeholders})""",
            ids,
        ).fetchall()

        busiest = conn.execute(
            f"""SELECT substr(created_at, 1, 10) AS day, COUNT(*) c
                FROM usage_events WHERE telegram_user_id IN ({placeholders})
                GROUP BY day ORDER BY c DESC, day DESC LIMIT 1""",
            ids,
        ).fetchone()

        # Peer comparison: totals per *account*, so someone with three linked
        # Telegram accounts is compared as one person, not three.
        peers = conn.execute(
            """
            SELECT l.account_id, COUNT(u.id) AS n
            FROM account_telegram_links l
            LEFT JOIN usage_events u ON u.telegram_user_id = l.telegram_user_id
            GROUP BY l.account_id
            """
        ).fetchall()

    by_category = categories.summarise(
        [{"platform": p, "media_kind": k, "quality": q} for p, k, q in rows]
    )
    top = max(by_category, key=lambda c: c["count"]) if any(c["count"] for c in by_category) else None

    comparison = _percentile(peers, account_id, total)

    return {
        "total": total,
        "last_30_days": last_30,
        "last_7_days": last_7,
        "minutes_saved": round(seconds / 60) if seconds else 0,
        "member_since": first_at[:10] if first_at else None,
        "by_category": by_category,
        "top_category": top["category"] if top else None,
        "busiest_day": {"date": busiest[0], "count": busiest[1]} if busiest else None,
        "comparison": comparison,
    }


def _percentile(peers, account_id: str, total: int) -> dict[str, Any]:
    """
    Where this account sits among the others.

    Returns nothing at all below a peer floor: with a handful of accounts a
    percentile is both meaningless and capable of pointing at one person.
    """
    counts = [n for _, n in peers]
    if len(counts) < MIN_PEERS_FOR_COMPARISON:
        return {"available": False, "peer_count": len(counts)}

    below = sum(1 for n in counts if n < total)
    same = sum(1 for n in counts if n == total)
    # Midpoint of the tied band, so everyone on zero is not told they beat
    # everyone else on zero.
    pct = round((below + same / 2) / len(counts) * 100)
    ordered = sorted(counts)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    return {
        "available": True,
        "peer_count": len(counts),
        "percentile": max(0, min(100, pct)),
        "median": median,
        "more_than_median": total > median,
    }


def _empty_stats() -> dict[str, Any]:
    return {
        "total": 0, "last_30_days": 0, "last_7_days": 0, "minutes_saved": 0,
        "member_since": None, "by_category": categories.summarise([]),
        "top_category": None, "busiest_day": None,
        "comparison": {"available": False, "peer_count": 0},
    }
