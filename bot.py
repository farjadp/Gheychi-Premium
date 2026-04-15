import logging
import re
import asyncio
import uuid
import time
from typing import Any, Optional

from telegram import (
    BotCommand,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import BadRequest

from config import ALLOWED_PLATFORMS, BOT_TOKEN, SUPPORT_CONTACT
from downloader import (
    get_video_info,
    download_video,
    download_audio,
    cleanup_file,
    VideoInfo,
)
from plans import build_plan_catalog_text, normalize_platform
from runtime_store import (
    add_log,
    evaluate_download_access,
    get_bot_user,
    get_usage_snapshot,
    init_logs_db,
    list_user_logs,
    load_settings,
    record_usage_event,
    upsert_bot_user,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

TELEGRAM_CONNECT_TIMEOUT = 30
TELEGRAM_POOL_TIMEOUT = 30
TELEGRAM_UPLOAD_TIMEOUT = 600

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?"
    r"(?:youtube\.com|youtu\.be|tiktok\.com|twitter\.com|x\.com|"
    r"instagram\.com|fb\.com|facebook\.com|vimeo\.com|"
    r"dailymotion\.com|reddit\.com|twitch\.tv|soundcloud\.com|"
    r"[\w\-]+\.[\w\-]+)"
    r"[^\s]*",
    re.IGNORECASE,
)

# Store pending downloads: {token: request_metadata}
pending_requests: dict[str, dict[str, Any]] = {}
PENDING_REQUEST_TTL = 1800  # 30 minutes


def _purge_expired_requests() -> None:
    now = time.monotonic()
    expired = [k for k, v in pending_requests.items() if now - v["created_at"] > PENDING_REQUEST_TTL]
    for k in expired:
        pending_requests.pop(k, None)

BOT_COMMANDS = [
    BotCommand("start", "شروع و نمایش منوی اصلی"),
    BotCommand("menu", "نمایش منوی سریع"),
    BotCommand("plans", "مشاهده پکیج‌ها"),
    BotCommand("myplan", "مشاهده پلن فعلی"),
    BotCommand("usage", "مشاهده سهمیه و اعتبار"),
    BotCommand("mylogs", "مشاهده لاگ‌های شخصی"),
    BotCommand("myid", "دریافت Telegram User ID"),
    BotCommand("support", "تماس با پشتیبانی"),
]


def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "نامشخص"
    total_seconds = int(seconds)
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def build_quality_keyboard(info: VideoInfo, request_token: str) -> InlineKeyboardMarkup:
    buttons = []

    if info.platform == "RadioJavan":
        buttons.append([InlineKeyboardButton("دانلود MP3", callback_data=f"dl|audio|{request_token}")])
        return InlineKeyboardMarkup(buttons)

    if info.formats:
        row = []
        for fmt in info.formats[:4]:  # show top 4 qualities
            h = fmt["height"]
            label = f"{h}p"
            row.append(InlineKeyboardButton(label, callback_data=f"dl|{h}|{request_token}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
    else:
        buttons.append([InlineKeyboardButton("بهترین کیفیت", callback_data=f"dl|best|{request_token}")])
        buttons.append([InlineKeyboardButton("کمترین حجم", callback_data=f"dl|worst|{request_token}")])

    buttons.append([InlineKeyboardButton("فقط صدا (MP3)", callback_data=f"dl|audio|{request_token}")])

    return InlineKeyboardMarkup(buttons)


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("آیدی من", callback_data="util|myid"),
                InlineKeyboardButton("پلن من", callback_data="util|myplan"),
            ],
            [
                InlineKeyboardButton("مصرف من", callback_data="util|usage"),
                InlineKeyboardButton("لاگ من", callback_data="util|mylogs"),
            ],
            [
                InlineKeyboardButton("پکیج‌ها", callback_data="util|plans"),
                InlineKeyboardButton("پشتیبانی", callback_data="util|support"),
            ],
        ]
    )


def build_usage_text(user_id: int) -> str:
    snapshot = get_usage_snapshot(user_id)
    expiry = snapshot["user"]["plan_expires_at"] or "نامحدود"
    lines = [
        f"*{snapshot['plan']['name']}*",
        f"انقضا: `{expiry}`",
    ]
    for rule in snapshot["rules"]:
        if rule["limit"] is None:
            lines.append(f"• {rule['platform']}: نامحدود")
            continue
        extra = ""
        if rule.get("max_duration_seconds"):
            extra = f" | حداکثر زمان: {rule['max_duration_seconds'] // 60} دقیقه"
        lines.append(
            f"• {rule['platform']}: {rule['used']}/{rule['limit']} در هر {rule['period_label']} | باقی‌مانده: {rule['remaining']}{extra}"
        )
    return "\n".join(lines)


def build_myplan_text(user_id: int) -> str:
    subscription = get_bot_user(user_id)
    expiry = subscription["plan_expires_at"] or "نامحدود"
    return (
        f"پلن فعلی: *{subscription['effective_plan']['name']}*\n"
        f"پلن ثبت‌شده: {subscription['assigned_plan']['name']}\n"
        f"قیمت: ${subscription['effective_plan']['price_usd']}/ماه\n"
        f"انقضا: `{expiry}`"
    )


def build_user_logs_text(user_id: int) -> str:
    logs = list_user_logs(user_id, limit=8)
    if not logs:
        return "هنوز لاگ شخصی برای شما ثبت نشده است."

    lines = ["آخرین رویدادهای شما"]
    for log in logs:
        platform = f" | {log['platform']}" if log.get("platform") else ""
        lines.append(f"• {log['created_at']} | {log['event_type']}{platform}")
        lines.append(f"  {log['message']}")
    return "\n".join(lines)


def build_support_contact() -> tuple[str, InlineKeyboardMarkup | None]:
    if not SUPPORT_CONTACT:
        return "اطلاعات پشتیبانی هنوز در سرور تنظیم نشده است.", None

    contact = SUPPORT_CONTACT.strip()
    if contact.startswith("@"):
        username = contact[1:]
        return (
            f"برای پشتیبانی با {contact} در تماس باش.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("تماس با پشتیبانی", url=f"https://t.me/{username}")]]
            ),
        )
    if contact.startswith("http://") or contact.startswith("https://"):
        return (
            "برای پشتیبانی از لینک زیر استفاده کن.",
            InlineKeyboardMarkup([[InlineKeyboardButton("پشتیبانی", url=contact)]]),
        )
    return f"پشتیبانی: {contact}", None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        upsert_bot_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    subscription = get_bot_user(user.id) if user else None
    settings = load_settings()
    platforms = "\n".join(f"• {p}" for p in settings["allowed_platforms"])
    text = (
        "سلام! به بات دانلودر خوش اومدی.\n\n"
        "کافیه لینک ویدئو رو بفرستی تا برات دانلود کنم.\n\n"
        f"پلن فعلی شما: *{subscription['effective_plan']['name']}*\n\n"
        f"*پلتفرم‌های پشتیبانی‌شده:*\n{platforms}\n\n"
        f"حداکثر حجم فایل: *{settings['max_file_size_mb']} مگابایت*\n\n"
        "دستورها:\n"
        "/menu - نمایش منوی سریع\n"
        "/plans - مشاهده پکیج‌ها\n"
        "/myplan - مشاهده پلن فعلی\n"
        "/mylogs - مشاهده لاگ‌های شخصی\n"
        "/usage - مشاهده سهمیه مصرف\n"
        "/myid - مشاهده آیدی عددی تلگرام\n"
        "/support - تماس با پشتیبانی"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_home_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "منوی سریع آماده است.\n"
        "از دکمه‌های زیر یا commandهای بات استفاده کن."
    )
    await update.message.reply_text(text, reply_markup=build_home_keyboard())


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_plan_catalog_text()
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def myplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    upsert_bot_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    await update.message.reply_text(build_myplan_text(user.id), parse_mode=ParseMode.MARKDOWN)


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    upsert_bot_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    await update.message.reply_text(build_usage_text(user.id), parse_mode=ParseMode.MARKDOWN)


async def mylogs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    upsert_bot_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    await update.message.reply_text(build_user_logs_text(user.id))


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    await update.message.reply_text(f"Telegram User ID شما:\n`{user.id}`", parse_mode=ParseMode.MARKDOWN)


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = build_support_contact()
    await update.message.reply_text(text, reply_markup=markup)


async def handle_utility_callback(query, context: ContextTypes.DEFAULT_TYPE):
    action = query.data.split("|", 1)[1]
    user = query.from_user
    if not user:
        return

    if action == "myid":
        await query.message.reply_text(
            f"Telegram User ID شما:\n`{user.id}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if action == "plans":
        await query.message.reply_text(build_plan_catalog_text(), parse_mode=ParseMode.MARKDOWN)
        return
    if action == "myplan":
        upsert_bot_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await query.message.reply_text(build_myplan_text(user.id), parse_mode=ParseMode.MARKDOWN)
        return
    if action == "usage":
        upsert_bot_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await query.message.reply_text(build_usage_text(user.id), parse_mode=ParseMode.MARKDOWN)
        return
    if action == "mylogs":
        upsert_bot_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await query.message.reply_text(build_user_logs_text(user.id))
        return
    if action == "support":
        text, markup = build_support_contact()
        await query.message.reply_text(text, reply_markup=markup)
        return


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text.strip()
    user = update.effective_user
    if user:
        upsert_bot_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    settings = load_settings()

    if not settings["downloads_enabled"]:
        await message.reply_text("دانلود موقتاً از پنل مدیریت غیرفعال شده است.")
        add_log(
            "INFO",
            "download_rejected",
            "درخواست به دلیل غیرفعال بودن دانلود رد شد.",
            metadata={"telegram_user_id": user.id if user else None},
        )
        return

    match = URL_PATTERN.search(text)
    if not match:
        await message.reply_text("لینک معتبری پیدا نکردم. لطفاً یک URL بفرست.")
        return

    url = match.group(0)
    await message.chat.send_action(ChatAction.TYPING)

    status_msg = await message.reply_text("در حال دریافت اطلاعات ویدئو...")

    try:
        info = await get_video_info(url)
    except Exception as e:
        add_log("ERROR", "metadata_failed", f"دریافت اطلاعات ناموفق بود: {str(e)[:200]}", url=url)
        await status_msg.edit_text(f"خطا در دریافت اطلاعات:\n`{str(e)[:300]}`", parse_mode=ParseMode.MARKDOWN)
        return

    platform_name = normalize_platform(info.platform, url)
    info.platform = platform_name
    platform_allowed = platform_name in settings["allowed_platforms"]
    fallback_allowed = "و بیش از ۱۰۰۰ سایت دیگر" in settings["allowed_platforms"]
    if not platform_allowed and not fallback_allowed:
        add_log(
            "INFO",
            "platform_blocked",
            "درخواست به دلیل محدودیت پلتفرم رد شد.",
            platform=platform_name,
            url=url,
            metadata={"telegram_user_id": user.id if user else None},
        )
        await status_msg.edit_text("این پلتفرم در پنل مدیریت غیرفعال شده است.")
        return

    access = evaluate_download_access(
        user.id,
        platform=platform_name,
        duration_seconds=int(info.duration) if info.duration else None,
    )
    if not access["allowed"]:
        add_log(
            "INFO",
            "subscription_blocked",
            access["reason"],
            platform=platform_name,
            url=url,
            metadata={"telegram_user_id": user.id if user else None},
        )
        await status_msg.edit_text(access["reason"])
        return

    add_log(
        "INFO",
        "metadata_loaded",
        "اطلاعات ویدئو با موفقیت دریافت شد.",
        platform=platform_name,
        url=url,
        metadata={
            "title": info.title,
            "duration": info.duration,
            "telegram_user_id": user.id if user else None,
            "plan_code": access["snapshot"]["user"]["effective_plan_code"],
        },
    )

    _purge_expired_requests()
    request_token = uuid.uuid4().hex[:16]
    pending_requests[request_token] = {
        "url": url,
        "telegram_user_id": user.id if user else None,
        "platform": platform_name,
        "duration_seconds": int(info.duration) if info.duration else None,
        "title": info.title,
        "uploader": info.uploader,
        "created_at": time.monotonic(),
    }

    caption = (
        f"*{info.title}*\n\n"
        f"پلتفرم: {info.platform}\n"
        f"آپلودر: {info.uploader}\n"
        f"مدت: {format_duration(info.duration)}\n\n"
        "کیفیت مورد نظر را انتخاب کن:"
    )

    keyboard = build_quality_keyboard(info, request_token)

    try:
        await status_msg.edit_text(caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except BadRequest:
        await status_msg.edit_text(caption, reply_markup=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("util|"):
        await handle_utility_callback(query, context)
        return
    if not data.startswith("dl|"):
        return

    parts = data.split("|", 2)
    if len(parts) != 3:
        return

    _, quality, request_token = parts
    request_data = pending_requests.get(request_token)
    if not request_data:
        await query.message.reply_text("این درخواست منقضی شده. لینک را دوباره بفرست.")
        return
    if query.from_user and request_data["telegram_user_id"] != query.from_user.id:
        await query.message.reply_text("این دکمه برای درخواست شما نیست.")
        return

    url = request_data["url"]
    platform_name = request_data["platform"]
    duration_seconds = request_data["duration_seconds"]
    user_id = request_data["telegram_user_id"]

    access = evaluate_download_access(
        user_id,
        platform=platform_name,
        duration_seconds=duration_seconds,
    )
    if not access["allowed"]:
        await query.message.reply_text(access["reason"])
        pending_requests.pop(request_token, None)
        return

    status_msg: Message = query.message
    await status_msg.edit_text("در حال دانلود... لطفاً صبر کن.")
    await status_msg.chat.send_action(ChatAction.UPLOAD_VIDEO)

    last_pct = {"val": -1}

    def on_progress(pct: int):
        if pct - last_pct["val"] >= 20:
            last_pct["val"] = pct
            asyncio.create_task(
                status_msg.edit_text(f"در حال دانلود... {pct}%")
            )

    if quality == "audio":
        result = await download_audio(url)
    else:
        result = await download_video(url, quality=quality, progress_callback=on_progress)

    if not result.success:
        add_log(
            "ERROR",
            "download_failed",
            result.error or "خطای نامشخص",
            platform=platform_name,
            url=url,
            metadata={"telegram_user_id": user_id},
        )
        await status_msg.edit_text(f"خطا: {result.error}")
        return

    await status_msg.edit_text("دانلود شد، در حال ارسال فایل...")

    try:
        file_path = result.file_path
        caption = result.title or "ویدئو"

        if quality == "audio":
            await status_msg.chat.send_action(ChatAction.UPLOAD_VOICE)
            with open(file_path, "rb") as f:
                await query.message.reply_audio(
                    audio=f,
                    title=caption,
                    caption=f"🎵 {caption}",
                    connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                    pool_timeout=TELEGRAM_POOL_TIMEOUT,
                    write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                    read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                )
        else:
            await status_msg.chat.send_action(ChatAction.UPLOAD_VIDEO)
            with open(file_path, "rb") as f:
                await query.message.reply_video(
                    video=f,
                    caption=f"🎬 {caption}",
                    supports_streaming=True,
                    connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                    pool_timeout=TELEGRAM_POOL_TIMEOUT,
                    write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                    read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                )

        add_log(
            "INFO",
            "download_sent",
            "فایل با موفقیت برای کاربر ارسال شد.",
            platform=platform_name,
            url=url,
            metadata={"quality": quality, "title": caption, "telegram_user_id": user_id},
        )
        record_usage_event(
            user_id,
            platform=platform_name,
            url=url,
            media_kind="audio" if quality == "audio" else "video",
            quality=quality,
            duration_seconds=duration_seconds,
            metadata={"title": caption},
        )
        await status_msg.delete()

    except Exception as e:
        logger.error("Send error: %s", e)
        add_log("ERROR", "send_failed", str(e)[:200], platform=platform_name, url=url, metadata={"telegram_user_id": user_id})
        # Try sending as document if video send fails
        try:
            with open(file_path, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    caption=f"📁 {result.title or 'فایل'}",
                    connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                    pool_timeout=TELEGRAM_POOL_TIMEOUT,
                    write_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                    read_timeout=TELEGRAM_UPLOAD_TIMEOUT,
                )
            add_log(
                "INFO",
                "document_fallback_sent",
                "فایل به‌صورت document ارسال شد.",
                platform=platform_name,
                url=url,
                metadata={"quality": quality, "title": result.title, "telegram_user_id": user_id},
            )
            record_usage_event(
                user_id,
                platform=platform_name,
                url=url,
                media_kind="document",
                quality=quality,
                duration_seconds=duration_seconds,
                metadata={"title": result.title},
            )
            await status_msg.delete()
        except Exception as e2:
            add_log(
                "ERROR",
                "document_fallback_failed",
                str(e2)[:200],
                platform=platform_name,
                url=url,
                metadata={"telegram_user_id": user_id},
            )
            await status_msg.edit_text(f"خطا در ارسال فایل: {str(e2)[:200]}")
    finally:
        cleanup_file(result.file_path)
        pending_requests.pop(request_token, None)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    from telegram.error import Conflict
    if isinstance(context.error, Conflict):
        logger.critical(
            "Conflict: another bot instance is running. "
            "Stop the other instance (Railway / another terminal) before running locally."
        )
        return
    logger.error("Unhandled error: %s", context.error, exc_info=context.error)
    add_log("ERROR", "unhandled_error", str(context.error)[:300])


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN تنظیم نشده! فایل .env را بررسی کن.")
    init_logs_db()
    save_note = {
        "supported_platforms": ALLOWED_PLATFORMS,
    }
    add_log("INFO", "bot_started", "بات اجرا شد.", metadata=save_note)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("plans", plans_command))
    app.add_handler(CommandHandler("myplan", myplan_command))
    app.add_handler(CommandHandler("usage", usage_command))
    app.add_handler(CommandHandler("mylogs", mylogs_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)

    logger.info("بات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
