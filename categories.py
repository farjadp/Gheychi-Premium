"""
دسته‌بندی موضوعی تاریخچه‌ی دانلود.

فایلی روی سرور نمی‌ماند — downloader بلافاصله بعد از ارسال پاکش می‌کند — پس
چیزی که دسته‌بندی می‌شود رکوردهای usage_events است، نه فایل.

دسته‌ها بر اساس «کاربر چه چیزی گرفته» گروه شده‌اند نه بر اساس نام سرویس. با
۱۴ پلتفرم مجاز به‌علاوه‌ی هزار سایت دیگر، فهرست پلتفرمی از همان اول شلوغ‌تر از
آن می‌شود که کسی نگاهش کند؛ شش دسته را می‌شود یک‌جا دید.

نکته: صدا بر پلتفرم اولویت دارد. کسی که از یوتیوب MP3 گرفته دنبال موسیقی بوده،
نه ویدیو، و در «موسیقی و صدا» پیدایش می‌کند نه در «ویدیو».
"""
from typing import Any

CATEGORY_VIDEO = "video"
CATEGORY_SOCIAL = "social"
CATEGORY_AUDIO = "audio"
CATEGORY_TELEGRAM = "telegram"
CATEGORY_ADULT = "adult"
CATEGORY_OTHER = "other"

CATEGORY_ORDER = [
    CATEGORY_VIDEO,
    CATEGORY_SOCIAL,
    CATEGORY_AUDIO,
    CATEGORY_TELEGRAM,
    CATEGORY_ADULT,
    CATEGORY_OTHER,
]

CATEGORY_LABELS = {
    CATEGORY_VIDEO:    {"en": "Video",           "fa": "ویدیو"},
    CATEGORY_SOCIAL:   {"en": "Social",          "fa": "شبکه‌های اجتماعی"},
    CATEGORY_AUDIO:    {"en": "Music & audio",   "fa": "موسیقی و صدا"},
    CATEGORY_TELEGRAM: {"en": "Telegram",        "fa": "تلگرام"},
    CATEGORY_ADULT:    {"en": "Adult",           "fa": "بزرگسال"},
    CATEGORY_OTHER:    {"en": "Other",           "fa": "سایر"},
}

_PLATFORM_CATEGORY = {
    "youtube": CATEGORY_VIDEO,
    "vimeo": CATEGORY_VIDEO,
    "dailymotion": CATEGORY_VIDEO,
    "twitch": CATEGORY_VIDEO,
    "instagram": CATEGORY_SOCIAL,
    "tiktok": CATEGORY_SOCIAL,
    "twitter/x": CATEGORY_SOCIAL,
    "twitter": CATEGORY_SOCIAL,
    "x": CATEGORY_SOCIAL,
    "facebook": CATEGORY_SOCIAL,
    "reddit": CATEGORY_SOCIAL,
    "linkedin": CATEGORY_SOCIAL,
    "soundcloud": CATEGORY_AUDIO,
    "radiojavan": CATEGORY_AUDIO,
    "telegram": CATEGORY_TELEGRAM,
    "pornhub": CATEGORY_ADULT,
}

_AUDIO_KINDS = {"audio", "mp3", "music"}


def categorise(platform: str | None, media_kind: str | None = None, quality: str | None = None) -> str:
    """
    Which bucket one download belongs to.

    Asking for audio wins over the platform it came from: someone who pulled an
    MP3 out of YouTube was after music, and looks for it under music.
    """
    kind = (media_kind or "").strip().lower()
    if kind in _AUDIO_KINDS or (quality or "").strip().lower() in _AUDIO_KINDS:
        # Telegram keeps its own bucket even for audio — it is the one category
        # that describes where the file was rescued from, not what it is, and
        # that is the distinction the product is sold on.
        if (platform or "").strip().lower() == "telegram":
            return CATEGORY_TELEGRAM
        return CATEGORY_AUDIO
    return _PLATFORM_CATEGORY.get((platform or "").strip().lower(), CATEGORY_OTHER)


def label(category: str, lang: str = "en") -> str:
    entry = CATEGORY_LABELS.get(category, CATEGORY_LABELS[CATEGORY_OTHER])
    return entry.get(lang, entry["en"])


def annotate(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a category to each history row, leaving the row otherwise intact."""
    for event in events:
        event["category"] = categorise(
            event.get("platform"), event.get("media_kind"), event.get("quality")
        )
    return events


def summarise(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Counts per category in a stable order, so the filter bar does not reshuffle
    itself every time the user downloads something.
    """
    counts = {c: 0 for c in CATEGORY_ORDER}
    for event in events:
        counts[categorise(event.get("platform"), event.get("media_kind"), event.get("quality"))] += 1
    return [
        {"category": c, "label_en": label(c, "en"), "label_fa": label(c, "fa"), "count": counts[c]}
        for c in CATEGORY_ORDER
    ]
