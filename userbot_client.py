"""
UserBot Client — Save Restricted Content
=========================================
از Pyrogram (MTProto) برای دریافت محتوای پروتکت‌شده تلگرام استفاده می‌کند.
Bot API معمولی نمی‌تواند محتوای restricted را دریافت کند؛
UserBot با اکانت شخصی و session string این کار را انجام می‌دهد.

رویکرد: UserBot فقط می‌خواند (read-only).
"""

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import — اگر pyrogram نصب نباشد، بقیه ماژول‌ها خراب نمی‌شوند
try:
    import pyrogram.utils
    pyrogram.utils.MIN_CHANNEL_ID = -10099999999999
    
    from pyrogram import Client
    from pyrogram.errors import (
        FloodWait,
        ChatAdminRequired,
        ChannelPrivate,
        UsernameInvalid,
        MessageIdInvalid,
    )
    PYROGRAM_AVAILABLE = True
except ImportError:
    PYROGRAM_AVAILABLE = False
    logger.warning("pyrogram نصب نشده. فیچر Save Restricted Content غیرفعال است.")


# ────────────────────────────────────────────────────
#  Data Classes
# ────────────────────────────────────────────────────

@dataclass
class TGMediaFile:
    """یک فایل دانلودشده از تلگرام"""
    file_path: str
    media_type: str  # "video" | "photo" | "audio" | "document" | "voice" | "animation"
    caption: str = ""
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class TGContent:
    success: bool
    error: str = ""
    files: list = None
    caption: str = ""
    is_album: bool = False
    dump_message_ids: list = None
    dump_chat_id: int = None


# ────────────────────────────────────────────────────
#  Link Parser
# ────────────────────────────────────────────────────

_TG_LINK_RE = re.compile(
    r"https?://t\.me/"
    r"(?:"
    r"(?P<username>[a-zA-Z0-9_]{5,32})/(?P<msg_id>\d+)"
    r"|c/(?P<chat_id>\d+)/(?:(?P<topic_id>\d+)/)?(?P<msg_id2>\d+)"
    r")",
    re.IGNORECASE,
)


def parse_tg_link(url: str):
    """
    لینک t.me را parse می‌کند.
    Returns: (chat_identifier, message_id) یا None
    """
    m = _TG_LINK_RE.search(url)
    if not m:
        return None

    if m.group("username"):
        return (m.group("username"), int(m.group("msg_id")))
    elif m.group("chat_id"):
        chat_id = int("-100" + m.group("chat_id"))
        return (chat_id, int(m.group("msg_id2")))

    return None


def is_tg_link(url: str) -> bool:
    """آیا این URL یک لینک پست تلگرام است؟"""
    return bool(_TG_LINK_RE.search(url))


def _get_file_size(msg) -> int:
    if msg.video: return getattr(msg.video, 'file_size', 0) or 0
    if msg.audio: return getattr(msg.audio, 'file_size', 0) or 0
    if msg.document: return getattr(msg.document, 'file_size', 0) or 0
    if msg.animation: return getattr(msg.animation, 'file_size', 0) or 0
    if msg.voice: return getattr(msg.voice, 'file_size', 0) or 0
    if msg.photo: return getattr(msg.photo, 'file_size', 0) or 0
    return 0


# ────────────────────────────────────────────────────
#  UserBot Client Manager
# ────────────────────────────────────────────────────

class UserBotClient:
    """Singleton wrapper دور Pyrogram Client."""

    def __init__(self):
        self._client = None
        self._started = False
        self._lock = asyncio.Lock()

    async def start(self, api_id: int, api_hash: str, session_string: str) -> bool:
        """UserBot را شروع می‌کند."""
        if not PYROGRAM_AVAILABLE:
            logger.error("pyrogram نصب نشده — UserBot نمی‌تواند start شود.")
            return False

        if not api_id or not api_hash or not session_string:
            logger.warning("TG_API_ID / TG_API_HASH / TG_SESSION_STRING تنظیم نشده‌اند. UserBot غیرفعال.")
            return False

        async with self._lock:
            if self._started:
                return True
            try:
                self._client = Client(
                    name="gheychi_userbot",
                    api_id=api_id,
                    api_hash=api_hash,
                    session_string=session_string,
                    in_memory=True,
                    no_updates=True,
                )
                await self._client.start()
                me = await self._client.get_me()
                logger.info("UserBot شروع شد: %s (@%s)", me.first_name, me.username)
                self._started = True
                return True
            except Exception as e:
                logger.error("UserBot start ناموفق بود: %s", e)
                self._client = None
                return False

    async def stop(self):
        """UserBot را متوقف می‌کند."""
        if self._client and self._started:
            try:
                await self._client.stop()
                logger.info("UserBot متوقف شد.")
            except Exception as e:
                logger.warning("UserBot stop: %s", e)
            finally:
                self._started = False
                self._client = None

    @property
    def is_ready(self) -> bool:
        return self._started and self._client is not None

    async def fetch_content(self, url: str, download_dir: str = "downloads", progress_callback=None) -> TGContent:
        """
        محتوای یک پیام تلگرام را دریافت و دانلود می‌کند.
        اگر پیام بخشی از آلبوم باشد، تمام اعضای آلبوم دانلود می‌شوند.
        """
        if not self.is_ready:
            return TGContent(success=False, error="userbot_not_ready")

        parsed = parse_tg_link(url)
        if not parsed:
            return TGContent(success=False, error="invalid_link")

        chat_id, message_id = parsed

        try:
            msg = await self._client.get_messages(chat_id, message_id)
            if not msg or msg.empty:
                return TGContent(success=False, error="message_not_found")
            if msg.media_group_id:
                return await self._fetch_album(chat_id, msg, download_dir, progress_callback)
            else:
                return await self._fetch_single(msg, download_dir, progress_callback)
        except Exception as e:
            err_str = str(e)
            if "FLOOD_WAIT" in err_str.upper():
                import re as _re
                m = _re.search(r"(\d+)", err_str)
                seconds = m.group(1) if m else "60"
                return TGContent(success=False, error=f"flood_wait:{seconds}")
            if any(x in err_str.upper() for x in ["CHANNEL_PRIVATE", "CHAT_ADMIN_REQUIRED", "FORBIDDEN"]):
                return TGContent(success=False, error="access_denied")
            if any(x in err_str.upper() for x in ["USERNAME_INVALID", "MESSAGE_ID_INVALID"]):
                return TGContent(success=False, error="invalid_link")
            logger.error("fetch_content خطا: %s", e, exc_info=True)
            return TGContent(success=False, error="download_failed")

    async def _fetch_single(self, msg, download_dir: str, progress_callback=None) -> TGContent:
        if not _has_media(msg):
            return TGContent(success=False, error="no_media")
        file_size = _get_file_size(msg)
        if file_size and file_size > 50 * 1024 * 1024:
            from config import DUMP_CHANNEL_ID
            if not DUMP_CHANNEL_ID:
                return TGContent(success=False, error=f"file_too_large:{file_size // (1024 * 1024)}:50")
            
            if progress_callback:
                await progress_callback("downloading")
            
            file_path, media_type, meta = await self._download_message(msg, download_dir)
            if not file_path:
                return TGContent(success=False, error="download_failed")
                
            if progress_callback:
                await progress_callback("uploading_to_dump")
                
            dump_msg = await self._upload_to_dump(file_path, media_type, msg.caption or "", meta)
            try:
                os.remove(file_path)
            except:
                pass
            
            if not dump_msg:
                return TGContent(success=False, error="download_failed")
            
            return TGContent(success=True, files=[], caption=msg.caption or "", is_album=False, dump_message_ids=[dump_msg.id], dump_chat_id=dump_msg.chat.id)

        if progress_callback:
            await progress_callback("downloading")
            
        file_path, media_type, meta = await self._download_message(msg, download_dir)
        if not file_path:
            return TGContent(success=False, error="download_failed")

        tg_file = TGMediaFile(file_path=file_path, media_type=media_type, caption=caption, **meta)
        return TGContent(success=True, files=[tg_file], caption=caption, is_album=False)

    async def _fetch_album(self, chat_id, first_msg, download_dir: str, progress_callback=None) -> TGContent:
        """تمام پیام‌های یک media group را دانلود می‌کند."""
        group_id = first_msg.media_group_id
        start_id = max(1, first_msg.id - 10)
        end_id = first_msg.id + 10

        try:
            messages = await self._client.get_messages(chat_id, list(range(start_id, end_id + 1)))
        except Exception as e:
            logger.warning("album fetch fallback to single: %s", e)
            return await self._fetch_single(first_msg, download_dir)

        group_msgs = [
            m for m in messages
            if m and not m.empty and m.media_group_id == group_id and _has_media(m)
        ]
        group_msgs.sort(key=lambda m: m.id)

        if not group_msgs:
            return await self._fetch_single(first_msg, download_dir)

        caption = next((m.caption for m in group_msgs if m.caption), "")

        files = []
        has_large_file = False

        for m in group_msgs:
            f_size = _get_file_size(m)
            if f_size and f_size > 50 * 1024 * 1024:
                from config import DUMP_CHANNEL_ID
                if not DUMP_CHANNEL_ID:
                    return TGContent(success=False, error=f"file_too_large:{f_size // (1024 * 1024)}:50")
                has_large_file = True

        if has_large_file:
            if progress_callback:
                await progress_callback("downloading")
                
            dump_ids = []
            for m in group_msgs:
                fp, mt, meta = await self._download_message(m, download_dir)
                if fp:
                    if progress_callback:
                        await progress_callback("uploading_to_dump")
                    d_msg = await self._upload_to_dump(fp, mt, m.caption or "", meta)
                    if d_msg:
                        dump_ids.append(d_msg.id)
                    try:
                        os.remove(fp)
                    except:
                        pass
            if not dump_ids:
                return TGContent(success=False, error="download_failed")
            return TGContent(success=True, files=[], caption=caption, is_album=True, dump_message_ids=dump_ids, dump_chat_id=dump_ids_chat)

        if progress_callback:
            await progress_callback("downloading")
            if file_path:
                files.append(TGMediaFile(
                    file_path=file_path,
                    media_type=media_type,
                    caption=m.caption or "",
                    **meta,
                ))

        if not files:
            return TGContent(success=False, error="download_failed")

        return TGContent(success=True, files=files, caption=caption, is_album=len(files) > 1)

    async def _download_message(self, msg, download_dir: str):
        """
        فایل مدیا یک پیام را دانلود می‌کند.
        Returns: (file_path, media_type, metadata_dict)
        """
        os.makedirs(download_dir, exist_ok=True)
        media_type = _detect_media_type(msg)
        if media_type is None:
            return None, "unknown", {}

        meta = {}
        if msg.video:
            meta = {"duration": msg.video.duration, "width": msg.video.width,
                    "height": msg.video.height, "file_name": msg.video.file_name,
                    "mime_type": msg.video.mime_type}
        elif msg.audio:
            meta = {"duration": msg.audio.duration, "file_name": msg.audio.file_name,
                    "mime_type": msg.audio.mime_type}
        elif msg.document:
            meta = {"file_name": msg.document.file_name, "mime_type": msg.document.mime_type}
        elif msg.animation:
            meta = {"duration": msg.animation.duration, "width": msg.animation.width,
                    "height": msg.animation.height, "mime_type": msg.animation.mime_type}

        try:
            ext = _guess_extension(media_type, meta.get("mime_type"), meta.get("file_name"))
            tmp_path = os.path.join(download_dir, f"tg_{msg.chat.id}_{msg.id}{ext}")
            downloaded = await self._client.download_media(msg, file_name=tmp_path)
            if not downloaded:
                return None, media_type, meta
            return str(downloaded), media_type, meta
        except Exception as e:
            logger.error("download_media خطا: %s", e)
            return None, media_type, meta

    async def _upload_to_dump(self, file_path, media_type, caption, meta):
        from config import DUMP_CHANNEL_ID
        try:
            from config import DUMP_CHANNEL_ID_RAW
            dump_target = DUMP_CHANNEL_ID_RAW
            if dump_target.startswith("http") or dump_target.startswith("t.me"):
                chat = await self._client.get_chat(dump_target)
                dump_target = chat.id
            else:
                dump_target = int(dump_target)
            
            if media_type == "video":
                return await self._client.send_video(dump_target, video=file_path, caption=caption, duration=meta.get("duration", 0), width=meta.get("width", 0), height=meta.get("height", 0))
            elif media_type == "audio":
                return await self._client.send_audio(dump_target, audio=file_path, caption=caption, duration=meta.get("duration", 0))
            elif media_type == "photo":
                return await self._client.send_photo(dump_target, photo=file_path, caption=caption)
            elif media_type == "animation":
                return await self._client.send_animation(dump_target, animation=file_path, caption=caption)
            elif media_type == "voice":
                return await self._client.send_voice(dump_target, voice=file_path, caption=caption, duration=meta.get("duration", 0))
            else:
                return await self._client.send_document(dump_target, document=file_path, caption=caption)
        except Exception as e:
            logger.error("Error uploading to dump channel: %s", e)
            return None


# ────────────────────────────────────────────────────
#  Helper Functions
# ────────────────────────────────────────────────────

def _has_media(msg) -> bool:
    return bool(
        msg.video or msg.photo or msg.audio or
        msg.document or msg.voice or msg.animation or
        msg.video_note
    )


def _detect_media_type(msg):
    if msg.video:       return "video"
    if msg.photo:       return "photo"
    if msg.audio:       return "audio"
    if msg.voice:       return "voice"
    if msg.animation:   return "animation"
    if msg.video_note:  return "video_note"
    if msg.document:    return "document"
    return None


def _guess_extension(media_type: str, mime_type=None, file_name=None) -> str:
    if file_name:
        ext = Path(file_name).suffix
        if ext:
            return ext
    MIME_EXT = {
        "video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-matroska": ".mkv",
        "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
        "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    }
    if mime_type and mime_type in MIME_EXT:
        return MIME_EXT[mime_type]
    TYPE_EXT = {
        "video": ".mp4", "photo": ".jpg", "audio": ".mp3",
        "voice": ".ogg", "animation": ".mp4", "video_note": ".mp4", "document": ".bin",
    }
    return TYPE_EXT.get(media_type, ".bin")



# ────────────────────────────────────────────────────
#  Global Singleton
# ────────────────────────────────────────────────────
userbot = UserBotClient()
