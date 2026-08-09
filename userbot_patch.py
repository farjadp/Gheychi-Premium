import re
with open("userbot_client.py", "r") as f:
    code = f.read()

get_file_size_func = """
def _get_file_size(msg) -> int:
    if msg.video: return getattr(msg.video, 'file_size', 0) or 0
    if msg.audio: return getattr(msg.audio, 'file_size', 0) or 0
    if msg.document: return getattr(msg.document, 'file_size', 0) or 0
    if msg.animation: return getattr(msg.animation, 'file_size', 0) or 0
    if msg.voice: return getattr(msg.voice, 'file_size', 0) or 0
    if msg.photo: return getattr(msg.photo, 'file_size', 0) or 0
    return 0

def _detect_media_type(msg) -> str:
"""

code = code.replace("def _detect_media_type(msg) -> str:", get_file_size_func)

fetch_single_patch = """
        if not _has_media(msg):
            return TGContent(success=False, error="no_media")

        file_size = _get_file_size(msg)
        if file_size and file_size > 50 * 1024 * 1024:
            return TGContent(success=False, error=f"file_too_large:{file_size // (1024 * 1024)}:50")

        caption = msg.caption or msg.text or ""
"""

code = code.replace("""
        if not _has_media(msg):
            return TGContent(success=False, error="no_media")

        caption = msg.caption or msg.text or ""
""", fetch_single_patch)

fetch_album_patch = """
        caption = next((m.caption for m in group_msgs if m.caption), "")

        files = []
        for m in group_msgs:
            f_size = _get_file_size(m)
            if f_size and f_size > 50 * 1024 * 1024:
                return TGContent(success=False, error=f"file_too_large:{f_size // (1024 * 1024)}:50")
                
            file_path, media_type, meta = await self._download_message(m, download_dir)
"""

code = code.replace("""
        caption = next((m.caption for m in group_msgs if m.caption), "")

        files = []
        for m in group_msgs:
            file_path, media_type, meta = await self._download_message(m, download_dir)
""", fetch_album_patch)

with open("userbot_client.py", "w") as f:
    f.write(code)

