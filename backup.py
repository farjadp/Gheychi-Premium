"""
پشتیبان‌گیری خودکار از دیتابیس.

چرا این فایل وجود دارد: volume روی Railway از پاک‌شدن با هر دیپلوی جلوگیری
می‌کند، اما از حذف تصادفی، خرابی فایل یا از دست رفتن خود volume محافظت نمی‌کند.
تا وقتی هویت کاربر فقط telegram_user_id بود، از دست رفتن دیتابیس قابل جبران بود
— کاربر دوباره /start می‌زد. با اکانت ایمیلی، از دست رفتنش یعنی نابودی اکانت
واقعی مردم. پس نسخه‌ی پشتیبان باید بیرون از خود volume نگهداری شود.

مقصد یک کانال خصوصی تلگرام است: رایگان، خارج از سرور، نسخه‌بندی‌شده، و روی
زیرساختی که این پروژه از قبل دارد.
"""
import asyncio
import logging
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import BOT_TOKEN, DATA_DIR

logger = logging.getLogger(__name__)

BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID", "").strip()
BACKUP_INTERVAL_SECONDS = int(os.getenv("BACKUP_INTERVAL_SECONDS", str(24 * 3600)))
TELEGRAM_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024

# Cookie files are re-created from the COOKIES_*_B64 env vars on every boot, so
# they are recoverable without a backup — and they are login credentials for
# other people's sites. Keeping them out means the archive holds no secrets.
_EXCLUDED_PREFIXES = ("cookies_",)

# The -wal and -shm sidecars belong to the *live* database. Their contents are
# already folded into the snapshot the backup API produces, and shipping a stale
# pair next to a clean snapshot is worse than useless: on restore SQLite may try
# to replay a WAL that does not match the file it sits beside.
_EXCLUDED_SUFFIXES = ("-wal", "-shm", "-journal")


def _snapshot_sqlite(source: Path, dest: Path) -> None:
    """
    Copy a live SQLite file through the online backup API.

    A plain file copy is not safe here: the databases run in WAL mode with the
    bot and the panel writing concurrently, so copying the .db alone can catch a
    torn page or miss everything still sitting in the -wal file. The backup API
    takes a consistent snapshot while writers carry on.
    """
    src_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    try:
        dst_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def build_backup_archive(dest_dir: str) -> Path:
    """Zip a consistent copy of everything in DATA_DIR worth keeping."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    archive = Path(dest_dir) / f"gheychi-data-{stamp}.zip"
    staging = Path(dest_dir) / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    data_dir = Path(DATA_DIR)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipf:
        if not data_dir.is_dir():
            logger.warning("Backup: DATA_DIR %s does not exist", data_dir)
            return archive
        for entry in sorted(data_dir.iterdir()):
            if not entry.is_file() or entry.name.startswith(_EXCLUDED_PREFIXES):
                continue
            if entry.name.endswith(_EXCLUDED_SUFFIXES):
                continue
            if entry.suffix == ".db":
                snapshot = staging / entry.name
                try:
                    _snapshot_sqlite(entry, snapshot)
                except sqlite3.Error as exc:
                    logger.error("Backup: could not snapshot %s: %s", entry.name, exc)
                    continue
                zipf.write(snapshot, entry.name)
            else:
                zipf.write(entry, entry.name)
    return archive


async def _upload(archive: Path, caption: str) -> None:
    from telegram import Bot

    bot = Bot(token=BOT_TOKEN)
    with archive.open("rb") as handle:
        await bot.send_document(
            chat_id=BACKUP_CHANNEL_ID,
            document=handle,
            filename=archive.name,
            caption=caption,
        )


def run_backup_once() -> bool:
    """Build and ship one backup. Returns True when the archive was delivered."""
    if not BACKUP_CHANNEL_ID:
        return False
    if not BOT_TOKEN:
        logger.error("Backup: BOT_TOKEN is not set, cannot upload")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        archive = build_backup_archive(tmp)
        size = archive.stat().st_size
        if size > TELEGRAM_UPLOAD_LIMIT_BYTES:
            # Telegram's own ceiling, the same 50 MB the product is capped at.
            logger.error(
                "Backup: archive is %.1f MB, over Telegram's 50 MB limit — not sent",
                size / (1024 * 1024),
            )
            return False

        caption = (
            f"🗄 Gheychi data backup\n"
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"{size / 1024:.0f} KB"
        )
        try:
            asyncio.run(_upload(archive, caption))
        except Exception as exc:
            logger.error("Backup: upload failed: %s", exc)
            return False

    logger.info("Backup: sent %s (%.0f KB)", archive.name, size / 1024)
    return True


def run_backup_loop() -> None:
    """Ship a backup every BACKUP_INTERVAL_SECONDS. No-op when unconfigured."""
    import time

    if not BACKUP_CHANNEL_ID:
        logger.warning(
            "Backup: BACKUP_CHANNEL_ID is not set — automated backups are OFF. "
            "The volume survives deploys but nothing survives losing the volume."
        )
        return

    while True:
        try:
            run_backup_once()
        except Exception as exc:
            logger.error("Backup: run failed: %s", exc)
        time.sleep(BACKUP_INTERVAL_SECONDS)
