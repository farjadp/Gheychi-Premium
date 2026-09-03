"""
Railway entrypoint — runs both the Telegram bot and Flask admin panel
as separate processes so they share the same SQLite database on disk.
"""
import base64
import multiprocessing
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(processName)s] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Mapping: env var holding base64 cookies → where to write the file
COOKIE_B64_VARS = {
    "COOKIES_YOUTUBE_B64":    "COOKIES_YOUTUBE",
    "COOKIES_INSTAGRAM_B64":  "COOKIES_INSTAGRAM",
    "COOKIES_TWITTER_B64":    "COOKIES_TWITTER",
    "COOKIES_TIKTOK_B64":     "COOKIES_TIKTOK",
    "COOKIES_FACEBOOK_B64":   "COOKIES_FACEBOOK",
    "COOKIES_SOUNDCLOUD_B64": "COOKIES_SOUNDCLOUD",
    "COOKIES_VIMEO_B64":      "COOKIES_VIMEO",
    "COOKIES_FILE_B64":       "COOKIES_FILE",
}

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def _decode_cookies() -> None:
    """
    For every COOKIES_*_B64 env var, decode the base64 content,
    write it to DATA_DIR, and set the corresponding COOKIES_* env var
    so downloader.py picks it up automatically.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for b64_var, path_var in COOKIE_B64_VARS.items():
        b64_content = os.environ.get(b64_var, "").strip()
        if not b64_content:
            continue
        try:
            decoded = base64.b64decode(b64_content)
            # Derive filename from the path var name, e.g. COOKIES_YOUTUBE → cookies_youtube.txt
            filename = path_var.lower().replace("cookies_", "cookies_") + ".txt"
            # Unless it's already set, build a sensible path
            dest = Path(os.environ.get(path_var) or str(DATA_DIR / filename))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(decoded)
            os.environ[path_var] = str(dest)
            logger.info("Cookie file written: %s → %s", b64_var, dest)
        except Exception as exc:
            logger.error("Failed to decode %s: %s", b64_var, exc)


def run_bot():
    from bot import main as bot_main
    bot_main()


def run_admin():
    from admin_panel import run_admin_panel
    run_admin_panel()


def run_housekeeping():
    """
    پاکسازی دوره‌ای فایل‌های موقتِ جامانده.

    اگر ارسال به کاربر با استثنا شکست بخورد، فایل دانلودشده روی دیسک
    باقی می‌ماند. روی یک volume کوچک این نشتی به‌مرور دیسک را پر می‌کند.

    این پروسه قبلاً هر ۱۲ ساعت `pip install -U yt-dlp` اجرا می‌کرد. آن کار
    حذف شد: روی فایل‌سیستم ephemeral با هر restart تکرار می‌شد و یک نسخه‌ی
    خرابِ yt-dlp می‌توانست بی‌هیچ هشداری پروداکشن را بخواباند. نسخه حالا در
    requirements.txt پین شده و با rebuild به‌روز می‌شود.
    """
    import time

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
    max_age = 3600  # فایل قدیمی‌تر از یک ساعت قطعاً یتیم است

    while True:
        try:
            if download_dir.is_dir():
                now = time.time()
                removed = 0
                freed = 0
                for entry in download_dir.iterdir():
                    try:
                        if not entry.is_file():
                            continue
                        if now - entry.stat().st_mtime < max_age:
                            continue
                        freed += entry.stat().st_size
                        entry.unlink()
                        removed += 1
                    except OSError:
                        continue
                if removed:
                    logger.info(
                        "Housekeeping: removed %d orphaned file(s), freed %.1f MB",
                        removed, freed / (1024 * 1024),
                    )
        except Exception as e:
            logger.error("Housekeeping failed: %s", e)
        time.sleep(1800)  # هر نیم‌ساعت


if __name__ == "__main__":
    _decode_cookies()

    bot_proc = multiprocessing.Process(target=run_bot, name="bot", daemon=False)
    admin_proc = multiprocessing.Process(target=run_admin, name="admin", daemon=False)
    housekeeping_proc = multiprocessing.Process(target=run_housekeeping, name="housekeeping", daemon=True)

    bot_proc.start()
    logger.info("Bot process started (pid=%s)", bot_proc.pid)

    admin_proc.start()
    logger.info("Admin panel process started (pid=%s)", admin_proc.pid)

    housekeeping_proc.start()
    logger.info("Housekeeping process started (pid=%s)", housekeeping_proc.pid)

    # If either process dies, shut down both
    try:
        while True:
            bot_proc.join(timeout=5)
            admin_proc.join(timeout=5)

            if not bot_proc.is_alive():
                logger.error("Bot process exited with code %s — shutting down.", bot_proc.exitcode)
                admin_proc.terminate()
                sys.exit(1)

            if not admin_proc.is_alive():
                logger.error("Admin panel process exited with code %s — shutting down.", admin_proc.exitcode)
                bot_proc.terminate()
                sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        bot_proc.terminate()
        admin_proc.terminate()
        bot_proc.join()
        admin_proc.join()
