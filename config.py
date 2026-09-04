import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# The public handle, without the @. It lived in forty places across the code and
# the site before, so changing bots meant a find-and-replace across twelve files.
BOT_USERNAME = os.getenv("BOT_USERNAME", "gheychipremium_bot").lstrip("@")
BOT_LINK = f"https://t.me/{BOT_USERNAME}"
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
DEFAULT_MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
if not BASE_URL.startswith("http://") and not BASE_URL.startswith("https://"):
    BASE_URL = "https://" + BASE_URL
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "fallback-secret-for-magic-links")

# ===== UserBot (Save Restricted Content) =====
# Get from https://my.telegram.org
_tg_api_id_raw = os.getenv("TG_API_ID", "0").strip().strip('"').strip("'")
TG_API_ID = int(_tg_api_id_raw) if _tg_api_id_raw and _tg_api_id_raw.isdigit() else 0
TG_API_HASH = os.getenv("TG_API_HASH", "").strip().strip('"').strip("'")
# Session string — generated once via generate_session.py

TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "").strip().strip('"').strip("'")
def _normalise_dump_channel(value: str) -> str:
    """
    Normalise DUMP_CHANNEL_ID to something the callers can trust.

    Unset used to default to the string "0", which is truthy in Python, so the
    `if not DUMP_CHANNEL_ID` guard never fired: a large file was downloaded in
    full and then uploaded to chat 0. Unset now means an empty string.

    Telegram shows a channel's peer id as a bare positive number while the API
    wants it prefixed with -100, so a bare number is prefixed here rather than
    left to fail at send time.
    """
    value = value.strip().strip('"').strip("'")
    if not value or value == "0":
        return ""
    if value.startswith("http") or value.startswith("t.me") or value.startswith("@"):
        return value
    if value.lstrip("-").isdigit() and not value.startswith("-"):
        return f"-100{value}"
    return value


DUMP_CHANNEL_ID_RAW = _normalise_dump_channel(os.getenv("DUMP_CHANNEL_ID", ""))
DUMP_CHANNEL_ID = DUMP_CHANNEL_ID_RAW



# Cobalt / RapidAPI Settings
# Cobalt / RapidAPI Settings
USE_COBALT_API = os.getenv("USE_COBALT_API", "True").lower() == "true"
COBALT_API_URL = os.getenv("COBALT_API_URL", "https://cobalt-api-v10-452069892013.europe-west1.run.app/")
COBALT_API_JWT = os.getenv("COBALT_API_JWT", "")
USE_RAPIDAPI = os.getenv("USE_RAPIDAPI", "False").lower() == "true"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "")
RAPIDAPI_YT_HOST = os.getenv("RAPIDAPI_YT_HOST", "youtube-info-download-api.p.rapidapi.com")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Maximum downloads running at once, across all users. Each one holds a
# yt-dlp process and a partial file on disk, so this is what keeps a busy
# minute from filling the container.
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))

ALLOWED_PLATFORMS = [
    "YouTube", "TikTok", "Twitter/X", "Instagram",
    "Facebook", "Vimeo", "Dailymotion", "Reddit",
    "Twitch", "SoundCloud", "RadioJavan", "PornHub",
    "Telegram",
    "و بیش از ۱۰۰۰ سایت دیگر",
]

SUPPORTED_PLATFORMS = ALLOWED_PLATFORMS
