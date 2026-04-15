from urllib.parse import urlparse

PERIOD_LABELS = {
    "day": "روز",
    "week": "هفته",
    "month": "ماه",
}

SUBSCRIPTION_PLANS = {
    "free": {
        "code": "free",
        "name": "پکیج رایگان",
        "price_usd": 0,
        "description": "شروع رایگان با سهمیه محدود برای Twitter/X و Instagram",
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
            {"platform": "YouTube", "limit": 5, "period": "week", "max_duration_seconds": 15 * 60},
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
            {"platform": "YouTube", "limit": 10, "period": "month", "max_duration_seconds": 30 * 60},
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
            {"platform": "YouTube", "limit": 10, "period": "month", "max_duration_seconds": 60 * 60},
        ],
    },
}

PLAN_ORDER = ["free", "starter", "standard", "pro"]


def get_plan(plan_code: str) -> dict:
    return SUBSCRIPTION_PLANS.get(plan_code, SUBSCRIPTION_PLANS["free"])


def list_plans() -> list[dict]:
    return [SUBSCRIPTION_PLANS[code] for code in PLAN_ORDER]


def get_plan_rule(plan_code: str, platform: str) -> dict | None:
    plan = get_plan(plan_code)
    for rule in plan["rules"]:
        if rule["platform"] == platform:
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
        base = f"{rule['platform']}: {rule['limit']} لینک در هر {PERIOD_LABELS[rule['period']]}"

    duration_limit = format_duration_limit(rule.get("max_duration_seconds"))
    if duration_limit:
        base = f"{base}، {duration_limit}"
    return base


def build_plan_catalog_text() -> str:
    chunks = []
    for plan in list_plans():
        lines = [f"*{plan['name']}* - ${plan['price_usd']}/ماه"]
        lines.extend(f"• {format_rule(rule)}" for rule in plan["rules"])
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)
