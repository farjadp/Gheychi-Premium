import os
import asyncio
import re
import uuid
import json
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
import subprocess

import yt_dlp

from config import DOWNLOAD_DIR
from runtime_store import get_max_file_size_bytes
from api_client import get_direct_media_url, is_cobalt_supported_url
import logging

logger = logging.getLogger(__name__)

@dataclass
class VideoInfo:
    title: str
    duration: Optional[int]  # seconds
    uploader: str
    platform: str
    thumbnail: Optional[str]
    formats: list = field(default_factory=list)  # list of available quality options


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None

def _extract_metadata(file_path: str) -> dict:
    """Extract width and height. Do NOT touch the file or extract duration (as it's often broken in HLS downlods)."""
    meta = {"width": None, "height": None, "duration": None}
    if not file_path or not os.path.exists(file_path) or not file_path.endswith(".mp4"):
        return meta

    try:
        cmd_probe = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", file_path
        ]
        out = subprocess.check_output(cmd_probe, text=True, timeout=10)
        data = json.loads(out)
        stream = data.get("streams", [{}])[0]
        meta["width"] = int(stream.get("width")) if stream.get("width") else None
        meta["height"] = int(stream.get("height")) if stream.get("height") else None
    except Exception as e:
        logger.warning(f"Metadata extraction failed: {e}")

    return meta


RADIOJAVAN_MP3_API = "https://play.radiojavan.com/api/p/mp3?id={track_id}"


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _ensure_download_dir() -> Path:
    path = Path(DOWNLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_radiojavan_url(url: str) -> Optional[dict]:
    parsed = urlparse(url)
    if "radiojavan.com" not in parsed.netloc.lower():
        return None

    if parsed.path.startswith("/redirect"):
        r = parse_qs(parsed.query).get("r", [""])[0]
        m = re.match(r"radiojavan://(mp3|podcast|video)/([^/?]+)", r)
        if m:
            return {"type": m.group(1), "id": m.group(2)}
    else:
        m = re.search(r"/(mp3|podcast|video)[^/]*/(?:mp3|podcast|video)?/?([^/?]+)", parsed.path)
        if m:
            if m.group(1) != m.group(2):
                return {"type": m.group(1), "id": m.group(2)}
    return None


def _fetch_radiojavan_info(obj_type: str, obj_id: str) -> dict:
    from urllib.parse import quote
    api_url = f"https://play.radiojavan.com/api/p/{obj_type}?id={quote(obj_id)}"
    req = Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://play.radiojavan.com/",
        },
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, destination: Path, progress_callback: Optional[Callable[[int], None]] = None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Referer": "https://twitter.com/",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=60) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            raise ValueError("لینک مستقیم منقضی شده یا مسدود شده است (فایل HTML به جای مدیا).")
            
        total = int(response.headers.get("Content-Length", "0"))
        with destination.open("wb") as f:
            downloaded = 0
            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total and progress_callback:
                    pct = int(downloaded / total * 100)
                    progress_callback(pct)


PLATFORM_COOKIE_ENV = {
    "youtube":   "COOKIES_YOUTUBE",
    "instagram": "COOKIES_INSTAGRAM",
    "twitter":   "COOKIES_TWITTER",
    "tiktok":    "COOKIES_TIKTOK",
    "facebook":  "COOKIES_FACEBOOK",
    "soundcloud":"COOKIES_SOUNDCLOUD",
    "vimeo":     "COOKIES_VIMEO",
}


def _get_cookies_file(platform: str | None) -> str | None:
    """Return path to cookies file for the given platform, or global fallback."""
    key = (platform or "").lower()
    # Try platform-specific first
    for pname, env_var in PLATFORM_COOKIE_ENV.items():
        if pname in key:
            path = os.environ.get(env_var)
            if path and os.path.exists(path):
                return path
    # Fall back to global COOKIES_FILE
    global_path = os.environ.get("COOKIES_FILE")
    if global_path and os.path.exists(global_path):
        return global_path
    return None


def _base_ydl_opts(output_template: str, platform: str | None = None) -> dict:
    max_file_size_bytes = get_max_file_size_bytes()
    opts = {
        "outtmpl": output_template,
        "ignoreconfig": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "max_filesize": max_file_size_bytes,
        "extractor_args": {"youtube": ["player_client=android"]},
    }
    cookies_file = _get_cookies_file(platform)
    if cookies_file:
        opts["cookiefile"] = cookies_file
    return opts


async def get_video_info(url: str) -> VideoInfo:
    """Fetch metadata without downloading."""
    rj_info = _parse_radiojavan_url(url)
    if rj_info:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, lambda: _fetch_radiojavan_info(rj_info["type"], rj_info["id"]))
        artist = info.get("artist") or info.get("podcast_artist")
        title_str = info.get("song") or info.get("title")
        title = " - ".join(part for part in [artist, title_str] if part) or info.get("title", f"RadioJavan {rj_info['type']}")
        return VideoInfo(
            title=title,
            duration=None,
            uploader=artist or "RadioJavan",
            platform="RadioJavan",
            thumbnail=info.get("photo") or info.get("thumbnail"),
            formats=[],
        )

    if is_cobalt_supported_url(url):
        return VideoInfo(
            title="ویدئو از طریق API",
            duration=None,
            uploader="کاربر",
            platform="API (Cobalt/Rapid)",
            thumbnail=None,
            formats=[],
        )

    opts = {
        "ignoreconfig": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    cookies_file = _get_cookies_file(url)
    if cookies_file:
        opts["cookiefile"] = cookies_file

    loop = asyncio.get_running_loop()

    def _fetch():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await loop.run_in_executor(None, _fetch)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        m = re.search(r"Unsupported URL: (https?://(?:play\.)?radiojavan\.com[^\s]+)", msg)
        if m:
            return await get_video_info(m.group(1))
        raise e

    formats = []
    seen = set()
    for f in info.get("formats", []):
        height = f.get("height")
        ext = f.get("ext", "")
        if height and ext in ("mp4", "webm") and height not in seen:
            seen.add(height)
            formats.append({"height": height, "format_id": f["format_id"], "ext": ext})

    formats.sort(key=lambda x: x["height"], reverse=True)

    return VideoInfo(
        title=info.get("title", "ویدئو"),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel") or "نامشخص",
        platform=info.get("extractor_key", "نامشخص"),
        thumbnail=info.get("thumbnail"),
        formats=formats,
    )


async def download_video(
    url: str,
    quality: str = "best",
    progress_callback: Optional[Callable[[int], None]] = None,
) -> DownloadResult:
    """
    Download a video.
    quality: 'best', 'worst', or a specific height like '720'
    """
    download_dir = _ensure_download_dir()
    request_id = uuid.uuid4().hex
    output_template = str(download_dir / f"{request_id}.%(ext)s")
    max_file_size_bytes = get_max_file_size_bytes()
    rj_info = _parse_radiojavan_url(url)

    if rj_info:
        return DownloadResult(
            success=False,
            error="لینک RadioJavan ترجیحاً به‌صورت فایل صوتی قابل دانلود است، در صورت امکان دکمه دانلود صوت را انتخاب کنید.",
        )

    if is_cobalt_supported_url(url):
        loop = asyncio.get_running_loop()
        api_result = await loop.run_in_executor(None, lambda: get_direct_media_url(url, quality))
        if api_result["success"]:
            direct_url = api_result["url"]
            destination = download_dir / f"{request_id}.mp4"
            try:
                def _do_download():
                    # progress_callback uses asyncio.create_task which needs the event loop thread.
                    # We must proxy it via call_soon_threadsafe to be safe from the executor thread.
                    def _safe_progress(pct: int):
                        if progress_callback:
                            loop.call_soon_threadsafe(progress_callback, pct)
                    _download_file(direct_url, destination, _safe_progress)
                await loop.run_in_executor(None, _do_download)
                if destination.exists() and destination.stat().st_size > 0:
                    file_size = destination.stat().st_size
                    if file_size > max_file_size_bytes:
                        destination.unlink(missing_ok=True)
                        return DownloadResult(success=False, error=f"فایل از محدودیت مگابایت بزرگتر است.")
                    meta = _extract_metadata(str(destination))
                    return DownloadResult(
                        success=True, file_path=str(destination), title="ویدئو", 
                        source=api_result.get("source", "API (Cobalt)"),
                        width=meta["width"], height=meta["height"], duration=meta["duration"]
                    )
            except Exception as e:
                logger.error(f"Failed to download from API direct URL: {e}")
        else:
            logger.warning(f"API attempt failed: {api_result.get('error')}. Falling back to yt-dlp...")

    # H.264 (avc) is the only codec Telegram inline player supports reliably.
    # We use a format selector that does NOT require merging (to avoid ffmpeg dependency).
    if quality == "best":
        format_selector = "best[vcodec^=avc][ext=mp4]/best[ext=mp4]/best"
    elif quality == "worst":
        format_selector = "worst[ext=mp4]/worst"
    elif quality == "audio":
        format_selector = "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio"
    else:
        # Specific height, e.g. "720"
        format_selector = f"best[height<={quality}][vcodec^=avc][ext=mp4]/best[height<={quality}][ext=mp4]/best"

    loop = asyncio.get_running_loop()
    downloaded_files: list[str] = []

    def _progress_hook(d: dict):
        if d["status"] == "finished":
            downloaded_files.append(d["filename"])
        elif d["status"] == "downloading" and progress_callback:
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                pct = int(downloaded / total * 100)
                loop.call_soon_threadsafe(progress_callback, pct)

    opts = _base_ydl_opts(output_template, platform=url)
    opts["format"] = format_selector
    opts["progress_hooks"] = [_progress_hook]
    opts["merge_output_format"] = "mp4"
    opts["postprocessors"] = [
        {
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }
    ]
    # Force H.264 + AAC re-encode so Telegram inline player always works.
    # Only triggered when the downloaded codec is NOT already H.264.
    opts["postprocessor_args"] = {
        "ffmpeg": [
            "-vcodec", "libx264",
            "-acodec", "aac",
            "-crf", "23",
            "-preset", "fast",
            "-movflags", "+faststart",
        ]
    }
    opts["prefer_ffmpeg"] = True

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info

    try:
        info = await loop.run_in_executor(None, _download)
        title = info.get("title", "ویدئو") if info else "ویدئو"

        # Find the actual downloaded file
        file_path = None
        if downloaded_files:
            # yt-dlp sometimes changes extension after merge
            candidate = downloaded_files[-1]
            # Check .mp4 variant too
            mp4_candidate = str(Path(candidate).with_suffix(".mp4"))
            if os.path.exists(mp4_candidate):
                file_path = mp4_candidate
            elif os.path.exists(candidate):
                file_path = candidate

        if not file_path:
            # Fallback: find any file with this request_id prefix
            matches = list(download_dir.glob(f"{request_id}.*"))
            if matches:
                file_path = str(matches[0])

        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            if file_size > max_file_size_bytes:
                os.remove(file_path)
                return DownloadResult(
                    success=False,
                    error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
                )
            meta = _extract_metadata(file_path)
            return DownloadResult(
                success=True, file_path=file_path, title=title,
                width=meta["width"], height=meta["height"], duration=meta["duration"]
            )

        return DownloadResult(success=False, error="فایل دانلود نشد.")

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        m = re.search(r"Unsupported URL: (https?://(?:play\.)?radiojavan\.com[^\s]+)", msg)
        if m:
            return await download_video(m.group(1), quality, progress_callback)
        if "Unsupported URL" in msg:
            return DownloadResult(success=False, error="این لینک پشتیبانی نمی‌شود.")
        if "Private video" in msg:
            return DownloadResult(success=False, error="ویدئو خصوصی است.")
        if "max filesize" in msg.lower() or "filesize" in msg.lower():
            return DownloadResult(
                success=False,
                error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
            )
        if "guest token" in msg.lower() or "bad guest token" in msg.lower():
            return DownloadResult(
                success=False,
                error="دانلود از Twitter/X نیاز به احراز هویت دارد.\nلطفاً با پشتیبانی تماس بگیر تا کوکی تنظیم شود.",
            )
        if "login required" in msg.lower() or "loginrequired" in msg.lower():
            return DownloadResult(success=False, error="این ویدئو نیاز به لاگین دارد.")
        return DownloadResult(success=False, error=f"خطا در دانلود: {msg[:200]}")
    except Exception as e:
        return DownloadResult(success=False, error=f"خطای غیرمنتظره: {str(e)[:200]}")


async def download_audio(url: str) -> DownloadResult:
    """Download audio-only (MP3)."""
    download_dir = _ensure_download_dir()
    request_id = uuid.uuid4().hex
    output_template = str(download_dir / f"{request_id}.%(ext)s")
    max_file_size_bytes = get_max_file_size_bytes()
    rj_info = _parse_radiojavan_url(url)

    if rj_info:
        loop = asyncio.get_running_loop()
        destination = download_dir / f"{request_id}.mp3"

        def _download_radiojavan():
            info = _fetch_radiojavan_info(rj_info["type"], rj_info["id"])
            audio_url = info.get("link") or info.get("hq_link")
            if not audio_url:
                raise ValueError("لینک فایل صوتی RadioJavan پیدا نشد.")
            _download_file(audio_url, destination)
            return info

        try:
            info = await loop.run_in_executor(None, _download_radiojavan)
            if destination.exists():
                file_size = destination.stat().st_size
                if file_size > max_file_size_bytes:
                    destination.unlink(missing_ok=True)
                    return DownloadResult(
                        success=False,
                        error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
                    )
                artist = info.get("artist") or info.get("podcast_artist")
                title_str = info.get("song") or info.get("title")
                title = " - ".join(
                    part for part in [artist, title_str] if part
                ) or info.get("title", f"RadioJavan {rj_info['type']}")
                return DownloadResult(success=True, file_path=str(destination), title=title)
            return DownloadResult(success=False, error="فایل صوتی RadioJavan دانلود نشد.")
        except Exception as e:
            return DownloadResult(success=False, error=f"خطا در دانلود RadioJavan: {str(e)[:200]}")

    opts = _base_ydl_opts(output_template, platform=url)
    opts["format"] = "bestaudio/best"
    opts["postprocessors"] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ]

    loop = asyncio.get_running_loop()

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info

    try:
        info = await loop.run_in_executor(None, _download)
        title = info.get("title", "صوت") if info else "صوت"

        # Use request_id to find the specific file, not the newest in dir
        file_path = str(download_dir / f"{request_id}.mp3")
        if not os.path.exists(file_path):
            return DownloadResult(success=False, error="فایل صوتی دانلود نشد.")

        file_size = os.path.getsize(file_path)
        if file_size > max_file_size_bytes:
            os.remove(file_path)
            return DownloadResult(
                success=False,
                error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
            )
        return DownloadResult(success=True, file_path=file_path, title=title)

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        m = re.search(r"Unsupported URL: (https?://(?:play\.)?radiojavan\.com[^\s]+)", msg)
        if m:
            return await download_audio(m.group(1))
        return DownloadResult(success=False, error=f"خطا: {str(e)[:200]}")
    except Exception as e:
        return DownloadResult(success=False, error=f"خطا: {str(e)[:200]}")


def cleanup_file(file_path: str):
    """Remove file after sending."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
