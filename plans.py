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

def get_plan(plan_code: str) -> dict:
    plans_dict = get_subscription_plans()
    return plans_dict.get(plan_code, plans_dict.get("free", {}))

from typing import Optional

def get_plan_rule(plan_code: str, platform: str) -> Optional[dict]:
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

def normalize_platform(raw_platform: str | None, url: str = "") -> str:
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower()
    platform = (raw_platform or "").lower()

    if "play.radiojavan.com" in host or "radiojavan" in platform:
        return "RadioJavan"
    if "youtube.com" in host or "youtu.be" in host or "youtube" in platform:
        return "YouTube"
    if "instagram.com" in host or "instagram" in platform:
        return "Instagram"
    if "twitter.com" in host or "x.com" in host or "twitter" in platform:
        return "Twitter/X"
    if "tiktok.com" in host or "tiktok" in platform:
        return "TikTok"
    if "facebook.com" in host or "fb.com" in host or "facebook" in platform:
        return "Facebook"
    if "vimeo.com" in host or "vimeo" in platform:
        return "Vimeo"
    if "soundcloud.com" in host or "soundcloud" in platform:
        return "SoundCloud"
    if "reddit.com" in host or "reddit" in platform:
        return "Reddit"
    if "twitch.tv" in host or "twitch" in platform:
        return "Twitch"
    if "dailymotion.com" in host or "dailymotion" in platform:
        return "Dailymotion"
    if "pornhub.com" in host or "pornhub" in platform:
        return "PornHub"
    return raw_platform or "نامشخص"

def format_duration_limit(seconds: int | None) -> str | None:
    if not seconds:
        return None
    minutes = seconds // 60
    return f"حداکثر {minutes} دقیقه"

def format_rule(rule: dict) -> str:
    if rule["limit"] is None:
        base = f"{rule['platform']}: نامحدود"
    else:
        base = f"{rule['platform']}: {rule['limit']} لینک در هر {PERIOD_LABELS.get(rule['period'], rule['period'])}"

    duration_limit = format_duration_limit(rule.get("max_duration_seconds"))
    if duration_limit:
        base = f"{base}، {duration_limit}"
    return base

def build_plan_catalog_text() -> str:
    chunks = []
    for plan in list_plans():
        lines = [f"*{plan['name']}* - ${plan['price_usd']}/ماه"]
        lines.extend(f"• {format_rule(rule)}" for rule in plan.get("rules", []))
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)
