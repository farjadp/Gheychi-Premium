import re

# 1. Update config.py
with open("config.py", "r") as f:
    config_code = f.read()

config_patch = """
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "").strip().strip('"').strip("'")
DUMP_CHANNEL_ID_RAW = os.getenv("DUMP_CHANNEL_ID", "0").strip().strip('"').strip("'")
DUMP_CHANNEL_ID = int(DUMP_CHANNEL_ID_RAW) if DUMP_CHANNEL_ID_RAW and DUMP_CHANNEL_ID_RAW.lstrip('-').isdigit() else 0
"""
config_code = config_code.replace("TG_SESSION_STRING = os.getenv(\"TG_SESSION_STRING\", \"\").strip().strip('\"').strip(\"'\")", config_patch)

with open("config.py", "w") as f:
    f.write(config_code)

# 2. Update userbot_client.py
with open("userbot_client.py", "r") as f:
    ub_code = f.read()

dataclass_patch = """
@dataclass
class TGContent:
    success: bool
    error: str = ""
    files: list[TGMediaFile] = None
    caption: str = ""
    is_album: bool = False
    dump_message_ids: list[int] = None
"""
ub_code = ub_code.replace("""
@dataclass
class TGContent:
    success: bool
    error: str = ""
    files: list[TGMediaFile] = None
    caption: str = ""
    is_album: bool = False
""", dataclass_patch.strip())

fetch_def_patch = """
    async def fetch_content(self, url: str, download_dir: str = "downloads", progress_callback=None) -> TGContent:
"""
ub_code = ub_code.replace("    async def fetch_content(self, url: str, download_dir: str = \"downloads\") -> TGContent:", fetch_def_patch.strip("\n"))

fetch_call_patch = """
            if msg.media_group_id:
                return await self._fetch_album(chat_id, msg, download_dir, progress_callback)
            else:
                return await self._fetch_single(msg, download_dir, progress_callback)
"""
ub_code = ub_code.replace("""
            if msg.media_group_id:
                return await self._fetch_album(chat_id, msg, download_dir)
            else:
                return await self._fetch_single(msg, download_dir)
""", fetch_call_patch.strip("\n"))

single_def_patch = """
    async def _fetch_single(self, msg, download_dir: str, progress_callback=None) -> TGContent:
"""
ub_code = ub_code.replace("    async def _fetch_single(self, msg, download_dir: str) -> TGContent:", single_def_patch.strip("\n"))

album_def_patch = """
    async def _fetch_album(self, chat_id, first_msg, download_dir: str, progress_callback=None) -> TGContent:
"""
ub_code = ub_code.replace("    async def _fetch_album(self, chat_id, first_msg, download_dir: str) -> TGContent:", album_def_patch.strip("\n"))

single_logic_patch = """
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
            
            return TGContent(success=True, files=[], caption=msg.caption or "", is_album=False, dump_message_ids=[dump_msg.id])

        if progress_callback:
            await progress_callback("downloading")
"""
ub_code = ub_code.replace("""
        file_size = _get_file_size(msg)
        if file_size and file_size > 50 * 1024 * 1024:
            return TGContent(success=False, error=f"file_too_large:{file_size // (1024 * 1024)}:50")

        caption = msg.caption or msg.text or ""
""", single_logic_patch.strip("\n"))

album_logic_patch = """
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
            return TGContent(success=True, files=[], caption=caption, is_album=True, dump_message_ids=dump_ids)

        if progress_callback:
            await progress_callback("downloading")
"""
ub_code = ub_code.replace("""
        for m in group_msgs:
            f_size = _get_file_size(m)
            if f_size and f_size > 50 * 1024 * 1024:
                return TGContent(success=False, error=f"file_too_large:{f_size // (1024 * 1024)}:50")
                
            file_path, media_type, meta = await self._download_message(m, download_dir)
""", """
        has_large_file = False
""" + album_logic_patch)

ub_code += """

    async def _upload_to_dump(self, file_path, media_type, caption, meta):
        from config import DUMP_CHANNEL_ID
        try:
            if media_type == "video":
                return await self._client.send_video(DUMP_CHANNEL_ID, video=file_path, caption=caption, duration=meta.get("duration", 0), width=meta.get("width", 0), height=meta.get("height", 0))
            elif media_type == "audio":
                return await self._client.send_audio(DUMP_CHANNEL_ID, audio=file_path, caption=caption, duration=meta.get("duration", 0))
            elif media_type == "photo":
                return await self._client.send_photo(DUMP_CHANNEL_ID, photo=file_path, caption=caption)
            elif media_type == "animation":
                return await self._client.send_animation(DUMP_CHANNEL_ID, animation=file_path, caption=caption)
            elif media_type == "voice":
                return await self._client.send_voice(DUMP_CHANNEL_ID, voice=file_path, caption=caption, duration=meta.get("duration", 0))
            else:
                return await self._client.send_document(DUMP_CHANNEL_ID, document=file_path, caption=caption)
        except Exception as e:
            logger.error("Error uploading to dump channel: %s", e)
            return None
"""

with open("userbot_client.py", "w") as f:
    f.write(ub_code)

# 3. Update tg_link_handler.py
with open("tg_link_handler.py", "r") as f:
    tg_code = f.read()

cb_patch = """
    async def _progress_cb(status: str):
        if status == "downloading":
            try:
                await status_msg.edit_text(get_text("tg_fetching", user_lang) + "\n⬇️ در حال دانلود از تلگرام...")
            except:
                pass
        elif status == "uploading_to_dump":
            try:
                await status_msg.edit_text("🔄 فایل بزرگ است. در حال آپلود به سرور واسطه (برای دور زدن محدودیت ۵۰ مگابایت)...")
            except:
                pass

    # ── دریافت محتوا از UserBot
    content = await userbot.fetch_content(url, download_dir=DOWNLOAD_DIR, progress_callback=_progress_cb)
"""
tg_code = tg_code.replace("    # ── دریافت محتوا از UserBot\n    content = await userbot.fetch_content(url, download_dir=DOWNLOAD_DIR)", cb_patch.strip("\n"))

dump_send_patch = """
    # ── ارسال فایل(ها) به کاربر
    try:
        if content.dump_message_ids:
            from config import DUMP_CHANNEL_ID
            await status_msg.edit_text("✅ در حال ارسال فایل به شما...")
            for msg_id in content.dump_message_ids:
                await context.bot.copy_message(chat_id=message.chat_id, from_chat_id=DUMP_CHANNEL_ID, message_id=msg_id)
        elif content.is_album and len(content.files) > 1:
"""
tg_code = tg_code.replace("""
    # ── ارسال فایل(ها) به کاربر
    try:
        if content.is_album and len(content.files) > 1:
""", dump_send_patch.strip("\n"))

with open("tg_link_handler.py", "w") as f:
    f.write(tg_code)
