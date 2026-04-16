import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
DEFAULT_MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "")

ALLOWED_PLATFORMS = [
    "YouTube", "TikTok", "Twitter/X", "Instagram",
    "Facebook", "Vimeo", "Dailymotion", "Reddit",
    "Twitch", "SoundCloud", "RadioJavan", "PornHub",
    "و بیش از ۱۰۰۰ سایت دیگر",
]

SUPPORTED_PLATFORMS = ALLOWED_PLATFORMS
