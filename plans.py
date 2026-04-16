import json
from pathlib import Path
from urllib.parse import urlparse
from config import DATA_DIR

PERIOD_LABELS = {
    "day": "روز",
    "week": "هفته",
    "month": "ماه",
}

DEFAULT_SUBSCRIPTION_PLANS = {
    "free": {
        "code": "free",
        "name": "پکیج رایگان",
        "price_usd": 0,
        "description": "شروع رایگان با سهمیه محدود",
        "rules": [
            {"platform": "Twitter/X", "limit": 5, "period": "month"},
            {"platform": "Instagram", "limit": 5, "period": "month"},
        ],
    },
    "starter": {
        "code": "starter",
        "name": "پکیج استارتر",
        "price_usd": 5,
        "description": "مناسب شروع با سهمیه روزانه و هفتگی کنترل‌شده",
        "rules": [
            {"platform": "RadioJavan", "limit": 3, "period": "month"},
            {"platform": "Twitter/X", "limit": 13, "period": "month"},
            {"platform": "Instagram", "limit": 13, "period": "day"},
            {"platform": "SoundCloud", "limit": 5, "period": "month"},
            {"platform": "YouTube", "limit": 5, "period": "week", "max_duration_seconds": 900},
            {"platform": "PornHub", "limit": 3, "period": "month", "max_duration_seconds": 1800},
        ],
    },
    "standard": {
        "code": "standard",
        "name": "پکیج استاندارد",
        "price_usd": 13,
        "description": "مصرف نامحدود برای RadioJavan، Twitter/X و Instagram به همراه TikTok و YouTube محدود",
        "rules": [
            {"platform": "RadioJavan", "limit": None, "period": None},
            {"platform": "Twitter/X", "limit": None, "period": None},
            {"platform": "Instagram", "limit": None, "period": None},
            {"platform": "TikTok", "limit": 13, "period": "month"},
            {"platform": "SoundCloud", "limit": 13, "period": "month"},
            {"platform": "YouTube", "limit": 10, "period": "month", "max_duration_seconds": 1800},
            {"platform": "PornHub", "limit": 5, "period": "month", "max_duration_seconds": 1800},
        ],
    },
    "pro": {
        "code": "pro",
        "name": "پکیج حرفه‌ای",
        "price_usd": 23,
        "description": "پلن حرفه‌ای با پلتفرم‌های نامحدود و YouTube محدود با سقف زمان بیشتر",
        "rules": [
            {"platform": "Twitter/X", "limit": None, "period": None},
            {"platform": "Instagram", "limit": None, "period": None},
            {"platform": "TikTok", "limit": None, "period": None},
            {"platform": "Facebook", "limit": None, "period": None},
            {"platform": "Vimeo", "limit": None, "period": None},
            {"platform": "SoundCloud", "limit": None, "period": None},
            {"platform": "YouTube", "limit": 10, "period": "month", "max_duration_seconds": 3600},
            {"platform": "PornHub", "limit": 13, "period": "month", "max_duration_seconds": 2700},
        ],
    },
}

PLANS_FILE = DATA_DIR / "plans.json"

def get_subscription_plans() -> dict:
    if not PLANS_FILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(PLANS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SUBSCRIPTION_PLANS, f, ensure_ascii=False, indent=2)
        return DEFAULT_SUBSCRIPTION_PLANS
    with open(PLANS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_subscription_plans(plans_dict: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PLANS_FILE, "w", encoding="utf-8") as f:
        json.dump(plans_dict, f, ensure_ascii=False, indent=2)

def list_plans() -> list[dict]:
    # Returns plans as a list preserving standard order if possible
    plans_dict = get_subscription_plans()
    order = ["free", "starter", "standard", "pro"]
    result = []
    # Add ordered ones first
    for code in order:
        if code in plans_dict:
            result.append(plans_dict[code])
    # Add any extra ones created dynamically
    for code, data in plans_dict.items():
        if code not in order:
            result.append(data)
    return result

def get_plan(plan_code: str) -> dict | None:
    plans_dict = get_subscription_plans()
    return plans_dict.get(plan_code)

def get_plan_rule(plan_code: str, platform: str) -> dict | None:
    plan = get_plan(plan_code)
    if not plan:
        return None
    for rule in plan.get("rules", []):
        if rule["platform"].lower() == platform.lower():
            return rule
        # YouTube fallback mapping
        if platform.lower() in ("yt", "youtube") and rule["platform"].lower() == "youtube":
            return rule
    return None

def extract_platform_from_url(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if not domain.startswith("www."):
        domain = "www." + domain

    if "youtube.com" in domain or "youtu.be" in domain:
        return "YouTube"
    if "tiktok.com" in domain:
        return "TikTok"
    if "twitter.com" in domain or "x.com" in domain:
        return "Twitter/X"
    if "instagram.com" in domain:
        return "Instagram"
    if "facebook.com" in domain or "fb.com" in domain or "fb.watch" in domain:
        return "Facebook"
    if "vimeo.com" in domain:
        return "Vimeo"
    if "dailymotion.com" in domain or "dai.ly" in domain:
        return "Dailymotion"
    if "reddit.com" in domain:
        return "Reddit"
    if "twitch.tv" in domain:
        return "Twitch"
    if "soundcloud.com" in domain:
        return "SoundCloud"
    if "radiojavan.com" in domain or "rj.app" in domain:
        return "RadioJavan"
    if "pornhub.com" in domain:
        return "PornHub"

    return "Other"
