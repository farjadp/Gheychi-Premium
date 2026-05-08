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
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
if not BASE_URL.startswith("http://") and not BASE_URL.startswith("https://"):
    BASE_URL = "https://" + BASE_URL
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "fallback-secret-for-magic-links")

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

ALLOWED_PLATFORMS = [
    "YouTube", "TikTok", "Twitter/X", "Instagram",
    "Facebook", "Vimeo", "Dailymotion", "Reddit",
    "Twitch", "SoundCloud", "RadioJavan", "PornHub",
    "و بیش از ۱۰۰۰ سایت دیگر",
]

SUPPORTED_PLATFORMS = ALLOWED_PLATFORMS
