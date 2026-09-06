"""
ارسال ایمیل از طریق Resend.

تنها وابستگی خارجیِ تازه‌ای که پنل کاربری اضافه می‌کند. تا پیش از این پروژه
هیچ راهی برای فرستادن ایمیل نداشت.

بدون RESEND_API_KEY خاموش می‌ماند و بلند لاگ می‌کند — همان الگوی بکاپ — تا
محیط توسعه بدون کلید کار کند و پروداکشنِ نیمه‌پیکربندی‌شده بی‌صدا شکست نخورد.
"""
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "Gheychi Premium <login@gheychee.xyz>").strip()
RESEND_ENDPOINT = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10

_SUBJECTS = {
    "fa": "کد ورود شما به قیچی پریمیوم",
    "en": "Your Gheychi Premium sign-in code",
}


def is_configured() -> bool:
    return bool(RESEND_API_KEY)


def _bodies(code: str, lang: str) -> tuple[str, str]:
    if lang == "fa":
        text = (
            f"کد ورود شما: {code}\n\n"
            "این کد ۵ دقیقه اعتبار دارد و فقط یک بار قابل استفاده است.\n"
            "اگر شما درخواست ورود نداده‌اید، این ایمیل را نادیده بگیرید."
        )
        html = (
            '<div dir="rtl" style="font-family:system-ui,sans-serif;font-size:16px;line-height:1.7">'
            "<p>کد ورود شما:</p>"
            f'<p style="font-size:30px;font-weight:700;letter-spacing:.2em">{code}</p>'
            "<p>این کد ۵ دقیقه اعتبار دارد و فقط یک بار قابل استفاده است.</p>"
            '<p style="color:#666">اگر شما درخواست ورود نداده‌اید، این ایمیل را نادیده بگیرید.</p>'
            "</div>"
        )
    else:
        text = (
            f"Your sign-in code: {code}\n\n"
            "It is valid for 5 minutes and works only once.\n"
            "If you did not request this, you can ignore this email."
        )
        html = (
            '<div style="font-family:system-ui,sans-serif;font-size:16px;line-height:1.7">'
            "<p>Your sign-in code:</p>"
            f'<p style="font-size:30px;font-weight:700;letter-spacing:.2em">{code}</p>'
            "<p>It is valid for 5 minutes and works only once.</p>"
            '<p style="color:#666">If you did not request this, you can ignore this email.</p>'
            "</div>"
        )
    return text, html


def send_login_code(email: str, code: str, lang: str = "en") -> bool:
    """
    Send a sign-in code. Returns True when Resend accepted it.

    Never raises: a mail provider having a bad day must not turn into a 500 on
    the sign-in form. The caller answers the user the same way either way, and
    the failure goes to the log.
    """
    lang = lang if lang in _SUBJECTS else "en"
    if not is_configured():
        logger.warning(
            "Email: RESEND_API_KEY is not set — no code was sent to %s. "
            "Sign-in by email cannot work until it is.",
            email,
        )
        return False

    text, html = _bodies(code, lang)
    payload = json.dumps(
        {
            "from": RESEND_FROM,
            "to": [email],
            "subject": _SUBJECTS[lang],
            "text": text,
            "html": html,
        }
    ).encode()

    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                logger.info("Email: sign-in code sent to %s", email)
                return True
            logger.error("Email: Resend returned HTTP %s for %s", response.status, email)
    except urllib.error.HTTPError as exc:
        # The body carries Resend's reason — an unverified domain, most often.
        detail = exc.read().decode(errors="replace")[:300]
        logger.error("Email: Resend rejected the send for %s: HTTP %s %s", email, exc.code, detail)
    except Exception as exc:
        logger.error("Email: could not reach Resend for %s: %s", email, exc)
    return False
