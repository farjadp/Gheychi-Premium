"""
TG Link Handler — Save Restricted Content
==========================================
Handler مجزا برای لینک‌های t.me در bot.py.
کاملاً مستقل از handle_url فعلی است و به امکانات موجود دست نمی‌زند.
"""

import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes

from config import DOWNLOAD_DIR
from locales import get_text
from runtime_store import (
    add_log,
    get_bot_user,
    upsert_bot_user,
)
from userbot_client import userbot, TGContent, TGMediaFile

logger = logging.getLogger(__name__)

TELEGRAM_CONNECT_TIMEOUT = 30
TELEGRAM_POOL_TIMEOUT = 30
TELEGRAM_UPLOAD_TIMEOUT = 600


async def handle_tg_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    """
    ورودی اصلی برای لینک‌های t.me.
    از bot.py فراخوانی می‌شود وقتی URL یک لینک تلگرام باشد.
    """
    message = update.message
    user = update.effective_user

    if user:
        upsert_bot_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )

    subscription = get_bot_user(user.id) if user else None
    user_lang = subscription.get("language_code", "fa") if subscription else "fa"

    # ── بررسی آماده بودن UserBot
    if not userbot.is_ready:
        await message.reply_text(get_text("tg_userbot_disabled", user_lang))
        add_log(
            "WARNING",
            "tg_userbot_disabled",
            "درخواست Save Restricted Content رد شد — UserBot پیکربندی نشده.",
            url=url,
            metadata={"telegram_user_id": user.id if user else None},
        )
        return

    await message.chat.send_action(ChatAction.TYPING)
    status_msg = await message.reply_text(get_text("tg_fetching", user_lang))

    # ── دریافت محتوا از UserBot
    content = await userbot.fetch_content(url, download_dir=DOWNLOAD_DIR)

    if not content.success:
        error_text = _map_error_to_text(content.error, user_lang)
        await status_msg.edit_text(error_text)
        add_log(
            "ERROR",
            "tg_fetch_failed",
            content.error or "unknown",
            url=url,
            metadata={"telegram_user_id": user.id if user else None},
        )
        return

    await status_msg.edit_text(get_text("tg_sending", user_lang))

    # ── ارسال فایل(ها) به کاربر
    try:
        if content.is_album and len(content.files) > 1:
            await _send_album(update, context, content, user_lang)
        else:
            await _send_single(update, context, content.files[0], user_lang)

        await status_msg.delete()
        add_log(
            "INFO",
            "tg_content_sent",
            f"محتوا با موفقیت ارسال شد ({len(content.files)} فایل).",
            url=url,
            metadata={"telegram_user_id": user.id if user else None, "is_album": content.is_album},
        )
    except Exception as e:
        logger.error("خطا در ارسال محتوای TG: %s", e, exc_info=True)
        await status_msg.edit_text(get_text("tg_download_failed", user_lang))
        add_log(
            "ERROR",
            "tg_send_failed",
            str(e)[:200],
            url=url,
            metadata={"telegram_user_id": user.id if user else None},
        )
    finally:
        # پاکسازی فایل‌های موقت
        for tg_file in content.files:
            try:
                if tg_file.file_path and os.path.exists(tg_file.file_path):
                    os.remove(tg_file.file_path)
            except Exception:
                pass


# ────────────────────────────────────────────────────
#  Send Helpers
# ────────────────────────────────────────────────────

async def _send_single(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tg_file: TGMediaFile,
    user_lang: str,
) -> None:
    """یک فایل مجزا را ارسال می‌کند."""
    caption = get_text("tg_caption", user_lang, title=tg_file.caption or "📁")
    file_path = tg_file.file_path
    media_type = tg_file.media_type

    with open(file_path, "rb") as f:
        if media_type == "video" or media_type == "animation" or media_type == "video_note":
            await update.message.reply_video(
                video=f,
                caption=caption,
                duration=tg_file.duration,
                width=tg_file.width,
                height=tg_file.height,
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
                write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
            )
        elif media_type == "audio":
            await update.message.reply_audio(
                audio=f,
                caption=caption,
                duration=tg_file.duration,
                parse_mode=ParseMode.MARKDOWN,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
                write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
            )
        elif media_type == "voice":
            await update.message.reply_voice(
                voice=f,
                caption=caption,
                duration=tg_file.duration,
                parse_mode=ParseMode.MARKDOWN,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
                write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
            )
        elif media_type == "photo":
            await update.message.reply_photo(
                photo=f,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
                write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
            )
        else:
            # document fallback
            await update.message.reply_document(
                document=f,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
                write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
            )


async def _send_album(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    content: TGContent,
    user_lang: str,
) -> None:
    """
    چند فایل را به صورت media group (آلبوم) ارسال می‌کند.
    اگر ارسال آلبوم ناموفق بود، یک‌به‌یک ارسال می‌کند.
    """
    from telegram import InputMediaVideo, InputMediaPhoto, InputMediaDocument, InputMediaAudio

    media_group = []
    open_files = []

    try:
        for i, tg_file in enumerate(content.files):
            f = open(tg_file.file_path, "rb")
            open_files.append(f)
            cap = content.caption if i == 0 else ""
            mt = tg_file.media_type

            if mt in ("video", "animation", "video_note"):
                media_group.append(InputMediaVideo(
                    media=f,
                    caption=cap if cap else None,
                    duration=tg_file.duration,
                    width=tg_file.width,
                    height=tg_file.height,
                    supports_streaming=True,
                ))
            elif mt == "photo":
                media_group.append(InputMediaPhoto(media=f, caption=cap if cap else None))
            elif mt == "audio":
                media_group.append(InputMediaAudio(media=f, caption=cap if cap else None, duration=tg_file.duration))
            else:
                media_group.append(InputMediaDocument(media=f, caption=cap if cap else None))

        await update.message.reply_media_group(
            media=media_group,
            connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
            pool_timeout=TELEGRAM_POOL_TIMEOUT,
            write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
            read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
        )
    except Exception as e:
        logger.warning("album send ناموفق، fallback به single: %s", e)
        # بستن فایل‌های باز
        for f in open_files:
            try:
                f.close()
            except Exception:
                pass
        open_files = []
        # ارسال یک‌به‌یک
        for tg_file in content.files:
            await _send_single(update, context, tg_file, user_lang)
    finally:
        for f in open_files:
            try:
                f.close()
            except Exception:
                pass


# ────────────────────────────────────────────────────
#  Error Mapping
# ────────────────────────────────────────────────────

def _map_error_to_text(error: str, user_lang: str) -> str:
    """کدهای خطا را به متن قابل نمایش برای کاربر تبدیل می‌کند."""
    if not error:
        return get_text("tg_download_failed", user_lang)


    if error.startswith("file_too_large:"):
        parts = error.split(":")
        size = parts[1] if len(parts) > 1 else "50+"
        limit = parts[2] if len(parts) > 2 else "50"
        return get_text("telegram_size_limit", user_lang, size_mb=size, max_size_mb=limit)

    if error.startswith("flood_wait:"):
        seconds = error.split(":")[1]
        return get_text("tg_flood_wait", user_lang, seconds=seconds)
    if error == "access_denied":
        return get_text("tg_access_denied", user_lang)
    if error == "invalid_link":
        return get_text("tg_invalid_link", user_lang)
    if error == "no_media":
        return get_text("tg_no_media", user_lang)
    if error == "userbot_not_ready":
        return get_text("tg_userbot_disabled", user_lang)

    return get_text("tg_download_failed", user_lang)
