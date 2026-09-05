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

# Ensure common paths are in PATH for ffmpeg/ffprobe and Node.js (for yt-dlp JS challenge solving)
for ext_path in ["/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.volta/bin"), os.path.expanduser("~/.volta/tools/image/node/22.21.1/bin")]:
    if ext_path not in os.environ.get("PATH", "") and os.path.exists(ext_path):
        os.environ["PATH"] = f"{ext_path}:{os.environ.get('PATH', '')}"

import yt_dlp

from config import DOWNLOAD_DIR, DATA_DIR
from plans import normalize_platform
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
    direct_url: Optional[str] = None

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
        # The site serves songs at /song/<slug> and the API answers for them on
        # the mp3 endpoint, so the two names have to be mapped.
        m = re.match(r"/song/([^/?]+)", parsed.path)
        if m:
            return {"type": "mp3", "id": m.group(1)}
        m = re.search(r"/(mp3|podcast|video)[^/]*/(?:mp3|podcast|video)?/?([^/?]+)", parsed.path)
        if m:
            if m.group(1) != m.group(2):
                return {"type": m.group(1), "id": m.group(2)}
    return None


def _is_youtube_url(url: str | None) -> bool:
    url_lower = (url or "").lower()
    return "youtube.com" in url_lower or "youtu.be" in url_lower


def _extract_youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id if re.fullmatch(r"[0-9A-Za-z_-]{11}", video_id or "") else None
    if "youtube.com" in host:
        query_id = parse_qs(parsed.query).get("v", [""])[0]
        if re.fullmatch(r"[0-9A-Za-z_-]{11}", query_id or ""):
            return query_id
        match = re.search(r"/(?:shorts|embed|live)/([0-9A-Za-z_-]{11})", parsed.path)
        if match:
            return match.group(1)
    return None


def _normalize_youtube_url(url: str) -> str:
    """Drop tracking params that sometimes confuse API fallbacks."""
    video_id = _extract_youtube_video_id(url)
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else url


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
    }
    
    # Platform-specific referers to prevent 403 on direct URLs
    url_lower = url.lower()
    if "twimg.com" in url_lower or "twitter.com" in url_lower or "x.com" in url_lower:
        headers["Referer"] = "https://twitter.com/"
    elif "googlevideo.com" in url_lower or "youtube.com" in url_lower or "youtu.be" in url_lower:
        headers["Referer"] = "https://www.youtube.com/"
        headers["Origin"] = "https://www.youtube.com"
        headers["sec-ch-ua"] = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"'
    elif "fbcdn.net" in url_lower or "facebook.com" in url_lower:
        headers["Referer"] = "https://www.facebook.com/"
    elif "cdninstagram.com" in url_lower or "instagram.com" in url_lower:
        headers["Referer"] = "https://www.instagram.com/"

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
    # Try platform-specific env var first
    for pname, env_var in PLATFORM_COOKIE_ENV.items():
        if pname in key:
            path = os.environ.get(env_var)
            if path and os.path.exists(path):
                return path
    # Fall back to global COOKIES_FILE env var
    global_path = os.environ.get("COOKIES_FILE")
    if global_path and os.path.exists(global_path):
        return global_path
    # Last resort: a cookie file placed on the volume by the operator.
    # Never commit one — a cookie jar exported from a browser carries the whole
    # Google session, not just YouTube, and this repo is public.
    local_cookie = os.path.join(str(DATA_DIR), "cookies.txt")
    if os.path.exists(local_cookie):
        return local_cookie
    return None


# Locate Node.js binary for yt-dlp JS challenge solving (needed for YouTube)
_NODE_PATHS = [
    os.path.expanduser("~/.volta/tools/image/node/22.21.1/bin/node"),
    os.path.expanduser("~/.volta/bin/node"),
    "/usr/local/bin/node",
    "/opt/homebrew/bin/node",
    "/usr/bin/node",
    "/bin/node",
    "node",  # fallback: let subprocess find it via PATH
]
_NODE_BIN = next((p for p in _NODE_PATHS if p == "node" or (os.path.isfile(p) and os.access(p, os.X_OK))), "node")


def _youtube_ydl_profiles(url: str) -> list[dict]:
    if not _is_youtube_url(url):
        profiles = [{"name": "default", "use_cookies": True, "clients": None}]
        # A cookie file that has expired makes the request worse than an
        # anonymous one, so a failed cookied attempt is retried without them.
        # Purely additive: a first attempt that succeeds never reaches this.
        if _get_cookies_file(url):
            profiles.append({"name": "default-no-cookies", "use_cookies": False, "clients": None})
        return profiles

    has_cookies = bool(_get_cookies_file(url))
    profiles: list[dict] = []
    if has_cookies:
        profiles.append({"name": "youtube-default-cookies", "use_cookies": True, "clients": None})
    profiles.append({"name": "youtube-default-no-cookies", "use_cookies": False, "clients": None})
    if has_cookies:
        profiles.append({
            "name": "youtube-mweb-cookies",
            "use_cookies": True,
            "clients": ["mweb"],
        })
    profiles.append({
        "name": "youtube-mweb-no-cookies",
        "use_cookies": False,
        "clients": ["mweb"],
    })
    if has_cookies:
        profiles.append({
            "name": "youtube-embedded-cookies",
            "use_cookies": True,
            "clients": ["web_embedded", "android"],
        })
    profiles.append({
        "name": "youtube-embedded-no-cookies",
        "use_cookies": False,
        "clients": ["web_embedded", "android"],
    })
    return profiles


# How long metadata extraction may take before the API placeholder is used
# instead. Only applies to platforms the API layer can download without it.
METADATA_TIMEOUT = int(os.getenv("METADATA_TIMEOUT_SECONDS", "20"))


def _network_opts(platform: str | None, youtube_clients: list[str] | None = None) -> dict:
    """
    Egress and YouTube-attestation options, shared by the metadata and download
    paths so a proxy configured for one is not missing from the other.

    YouTube signs its media URLs against the requesting IP — "ip" appears in the
    sparams list — so metadata and media must leave from the same address. There
    is no cheap "proxy only the small request" split.
    """
    opts: dict = {}

    proxy = os.getenv("YTDLP_PROXY", "").strip()
    if proxy:
        opts["proxy"] = proxy

    if not _is_youtube_url(platform):
        return opts

    extractor_args: dict[str, dict[str, list[str]]] = {}
    youtube_args: dict[str, list[str]] = {}
    if youtube_clients:
        youtube_args["player_client"] = youtube_clients

    # PO tokens expire within hours, so they are minted per request by the
    # bgutil provider plugin rather than pasted into an env var. This points the
    # plugin at the provider server; unset, it uses its own 127.0.0.1:4416.
    pot_base_url = os.getenv("BGUTIL_POT_BASE_URL", "").strip()
    if pot_base_url:
        extractor_args["youtubepot-bgutilhttp"] = {"base_url": [pot_base_url]}

    # Manual override for debugging one token by hand. Not a mechanism.
    youtube_po_token = os.getenv("YOUTUBE_PO_TOKEN", "").strip()
    if youtube_po_token:
        youtube_args["po_token"] = [youtube_po_token]
    youtube_visitor_data = os.getenv("YOUTUBE_VISITOR_DATA", "").strip()
    if youtube_visitor_data:
        youtube_args["visitor_data"] = [youtube_visitor_data]

    if youtube_args:
        extractor_args["youtube"] = youtube_args
    if extractor_args:
        opts["extractor_args"] = extractor_args
    return opts


def _base_ydl_opts(
    output_template: str,
    platform: str | None = None,
    *,
    use_cookies: bool = True,
    youtube_clients: list[str] | None = None,
) -> dict:
    max_file_size_bytes = get_max_file_size_bytes()
    cookies_file = _get_cookies_file(platform) if use_cookies else None
    opts = {
        "outtmpl": output_template,
        "ignoreconfig": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "max_filesize": max_file_size_bytes,
        "js_runtimes": {"node": {"path": _NODE_BIN}},
    }
    opts.update(_network_opts(platform, youtube_clients))

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

    opts = {
        "ignoreconfig": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "js_runtimes": {"node": {"path": _NODE_BIN}},
    }
    opts.update(_network_opts(url))
    cookies_file = _get_cookies_file(url)
    if cookies_file:
        opts["cookiefile"] = cookies_file

    loop = asyncio.get_running_loop()

    def _fetch():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError:
            # A stale cookie file is worse than none: an expired YouTube session
            # answers the API with 400 rather than falling back to anonymous
            # access. The download path already tries both, so metadata does too
            # instead of failing on a cookie nobody has refreshed.
            if not opts.get("cookiefile"):
                raise
            retry = dict(opts)
            retry.pop("cookiefile", None)
            logger.warning("retrying metadata for %s without cookies", url)
            with yt_dlp.YoutubeDL(retry) as ydl:
                return ydl.extract_info(url, download=False)

    # Metadata is a convenience, not the job. On a datacenter IP an extraction
    # can stall behind bot checks, and for the platforms the API layer can
    # download anyway there is no reason to make the user wait for it: fall back
    # to the placeholder and let the download proceed.
    try:
        if is_cobalt_supported_url(url):
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _fetch), timeout=METADATA_TIMEOUT
            )
        else:
            info = await loop.run_in_executor(None, _fetch)
    except asyncio.TimeoutError:
        logger.warning("metadata timed out after %ss for %s, falling back to API", METADATA_TIMEOUT, url)
        return VideoInfo(
            title=normalize_platform(None, url),
            duration=None,
            uploader="",
            platform=normalize_platform(None, url),
            thumbnail=None,
            formats=[],
        )
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        m = re.search(r"Unsupported URL: (https?://(?:play\.)?radiojavan\.com[^\s]+)", msg)
        if m:
            return await get_video_info(m.group(1))
        # Metadata used to be skipped entirely for these platforms, which meant
        # duration was always None — and a null duration silently disables every
        # plan's max_duration_seconds cap. Read it properly, and fall back to a
        # placeholder only when extraction genuinely fails, since the download
        # itself can still succeed through the API layer.
        if is_cobalt_supported_url(url):
            logger.warning("metadata extraction failed for %s, falling back to API: %s", url, str(e)[:200])
            return VideoInfo(
                title=normalize_platform(None, url),
                duration=None,
                uploader="",
                platform=normalize_platform(None, url),
                thumbnail=None,
                formats=[],
            )
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


def _download_error_result(e: yt_dlp.utils.DownloadError, max_file_size_bytes: int) -> DownloadResult:
    msg = str(e)
    msg_lower = msg.lower()
    if "Unsupported URL" in msg:
        return DownloadResult(success=False, error="این لینک پشتیبانی نمی‌شود.")
    if "Private video" in msg:
        return DownloadResult(success=False, error="ویدئو خصوصی است.")
    if "max filesize" in msg_lower or "filesize" in msg_lower:
        return DownloadResult(
            success=False,
            error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
        )
    if "guest token" in msg_lower or "bad guest token" in msg_lower:
        return DownloadResult(
            success=False,
            error="دانلود از Twitter/X نیاز به احراز هویت دارد.\nلطفاً با پشتیبانی تماس بگیر تا کوکی تنظیم شود.",
        )
    if (
        "login required" in msg_lower
        or "loginrequired" in msg_lower
        or ("confirm" in msg_lower and "not a bot" in msg_lower)
    ):
        return DownloadResult(success=False, error="youtube_auth_required")
    if "http error 403" in msg_lower and "youtube" in msg_lower:
        return DownloadResult(success=False, error="youtube_auth_required")
    if "http error 400" in msg_lower and "youtube" in msg_lower:
        return DownloadResult(success=False, error="youtube_cookie_invalid")
    return DownloadResult(success=False, error=f"خطا در دانلود: {msg[:200]}")


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
    source_url = _normalize_youtube_url(url) if _is_youtube_url(url) else url
    rj_info = _parse_radiojavan_url(source_url)

    if rj_info:
        return DownloadResult(
            success=False,
            error="لینک RadioJavan ترجیحاً به‌صورت فایل صوتی قابل دانلود است، در صورت امکان دکمه دانلود صوت را انتخاب کنید.",
        )

    # YouTube used to be held back from this layer because the generic handler
    # answered a YouTube link with a googlevideo URL signed against the requesting
    # IP, which 403s from a datacenter. That is no longer how the request is
    # served: a dedicated provider now runs ahead of the generic one and returns a
    # file on its own CDN with no such binding. Meanwhile yt-dlp cannot reach
    # YouTube from this host at all — every profile answers "Sign in to confirm
    # you're not a bot" — so going there first only spent about ten seconds per
    # request on a certain failure.
    api_tried = False
    if is_cobalt_supported_url(source_url):
        api_tried = True
        loop = asyncio.get_running_loop()
        api_result = await loop.run_in_executor(None, lambda: get_direct_media_url(source_url, quality))
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
                        width=meta["width"], height=meta["height"], duration=meta["duration"],
                        direct_url=direct_url
                    )
            except Exception as e:
                logger.error(f"Failed to download from API direct URL: {e}")
        else:
            logger.warning(f"API attempt failed: {api_result.get('error')}. Falling back to yt-dlp...")

    # H.264 (avc) is the only codec Telegram inline player supports reliably.
    # We use a format selector that does NOT require merging (to avoid ffmpeg dependency).
    if quality == "best":
        format_selector = "best[vcodec^=avc][ext=mp4][protocol^=http]/best[ext=mp4][protocol^=http]/best[vcodec^=avc][ext=mp4]/best[ext=mp4]/best"
    elif quality == "worst":
        format_selector = "worst[ext=mp4][protocol^=http]/worst[ext=mp4]/worst"
    elif quality == "audio":
        format_selector = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        # Specific height, e.g. "720"
        format_selector = f"best[height<={quality}][vcodec^=avc][ext=mp4][protocol^=http]/best[height<={quality}][ext=mp4][protocol^=http]/best[height<={quality}][vcodec^=avc][ext=mp4]/best[height<={quality}][ext=mp4]/best[height<={quality}]/best"
    
    loop = asyncio.get_running_loop()
    last_download_error: yt_dlp.utils.DownloadError | None = None
    last_direct_url: str | None = None

    for profile in _youtube_ydl_profiles(source_url):
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

        opts = _base_ydl_opts(
            output_template,
            platform=source_url,
            use_cookies=profile["use_cookies"],
            youtube_clients=profile["clients"],
        )
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
                info = ydl.extract_info(source_url, download=True)
                return info

        try:
            logger.info("yt-dlp download attempt: %s", profile["name"])
            info = await loop.run_in_executor(None, _download)
        except yt_dlp.utils.DownloadError as e:
            last_download_error = e
            logger.warning("yt-dlp attempt failed (%s): %s", profile["name"], str(e)[:300])
            if _is_youtube_url(source_url):
                continue
            break

        title = info.get("title", "ویدئو") if info else "ویدئو"

        # A googlevideo URL is signed against the IP that requested it — "ip" is
        # inside the sparams list — so handing one to the user guarantees a 403
        # from their device. Offer the direct link only where it can actually
        # be fetched from somewhere else.
        direct_url = None
        if info and not _is_youtube_url(source_url):
            url_cand = info.get("url")
            if url_cand and ".m3u8" not in url_cand and "manifest" not in url_cand:
                direct_url = url_cand
            if not direct_url and "requested_formats" in info:
                for f in info["requested_formats"]:
                    if f.get("vcodec") != "none" and "url" in f:
                        cand = f["url"]
                        if cand and ".m3u8" not in cand and "manifest" not in cand:
                            direct_url = cand
                            break
        last_direct_url = direct_url

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
            matches = [
                path for path in download_dir.glob(f"{request_id}.*")
                if not path.name.endswith(".part") and path.suffix != ".ytdl"
            ]
            if matches:
                file_path = str(matches[0])

        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            if file_size > max_file_size_bytes:
                os.remove(file_path)
                return DownloadResult(
                    success=False,
                    error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
                    direct_url=direct_url
                )
            meta = _extract_metadata(file_path)
            return DownloadResult(
                success=True, file_path=file_path, title=title,
                width=meta["width"], height=meta["height"], duration=meta["duration"],
                direct_url=direct_url
            )

        if info:
            size = info.get("filesize") or info.get("filesize_approx", 0)
            if size and size > max_file_size_bytes:
                return DownloadResult(success=False, error=f"exceeded_size:{size}", direct_url=direct_url)

        if not _is_youtube_url(source_url):
            return DownloadResult(success=False, error="فایل دانلود نشد.", direct_url=direct_url)
        logger.warning("yt-dlp attempt produced no file (%s)", profile["name"])

    # Only reachable when the block above was skipped, so the provider is never
    # billed twice for one request — each call costs four units of a 500-a-day
    # allowance.
    if _is_youtube_url(source_url) and not api_tried:
        api_result = await loop.run_in_executor(None, lambda: get_direct_media_url(source_url, quality))
        if api_result.get("success"):
            destination = download_dir / f"{request_id}.mp4"
            try:
                def _do_download():
                    def _safe_progress(pct: int):
                        if progress_callback:
                            loop.call_soon_threadsafe(progress_callback, pct)
                    _download_file(api_result["url"], destination, _safe_progress)
                await loop.run_in_executor(None, _do_download)
                if destination.exists() and destination.stat().st_size > 0:
                    file_size = destination.stat().st_size
                    if file_size > max_file_size_bytes:
                        destination.unlink(missing_ok=True)
                        return DownloadResult(success=False, error=f"فایل از محدودیت مگابایت بزرگتر است.")
                    meta = _extract_metadata(str(destination))
                    return DownloadResult(
                        success=True, file_path=str(destination), title="ویدئو",
                        source=api_result.get("source", "API"),
                        width=meta["width"], height=meta["height"], duration=meta["duration"],
                        direct_url=api_result["url"],
                    )
            except Exception as e:
                logger.error("YouTube API fallback direct download failed: %s", e)

    if last_download_error:
        msg = str(last_download_error)
        m = re.search(r"Unsupported URL: (https?://(?:play\.)?radiojavan\.com[^\s]+)", msg)
        if m:
            return await download_video(m.group(1), quality, progress_callback)
        result = _download_error_result(last_download_error, max_file_size_bytes)
        result.direct_url = last_direct_url
        return result

    return DownloadResult(success=False, error="فایل دانلود نشد.", direct_url=last_direct_url)


async def download_audio(
    url: str,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> DownloadResult:
    """Download audio-only (MP3)."""
    download_dir = _ensure_download_dir()
    request_id = uuid.uuid4().hex
    output_template = str(download_dir / f"{request_id}.%(ext)s")
    max_file_size_bytes = get_max_file_size_bytes()
    source_url = _normalize_youtube_url(url) if _is_youtube_url(url) else url
    rj_info = _parse_radiojavan_url(source_url)

    def _extract_audio_duration(f_path: str) -> Optional[int]:
        try:
            cmd_probe = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", f_path
            ]
            out = subprocess.check_output(cmd_probe, text=True, timeout=10)
            return int(float(out.strip()))
        except Exception:
            return None

    if rj_info:
        loop = asyncio.get_running_loop()
        destination = download_dir / f"{request_id}.mp3"

        def _download_radiojavan():
            info = _fetch_radiojavan_info(rj_info["type"], rj_info["id"])
            audio_url = info.get("link") or info.get("hq_link")
            if not audio_url:
                raise ValueError("لینک فایل صوتی RadioJavan پیدا نشد.")
            
            def _safe_progress(pct: int):
                if progress_callback:
                    loop.call_soon_threadsafe(progress_callback, pct)
            _download_file(audio_url, destination, progress_callback=_safe_progress)
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
                
                # Extract duration for correct UI parsing
                duration = _extract_audio_duration(str(destination))
                
                return DownloadResult(success=True, file_path=str(destination), title=title, duration=duration)
            return DownloadResult(success=False, error="فایل صوتی RadioJavan دانلود نشد.")
        except Exception as e:
            return DownloadResult(success=False, error=f"خطا در دانلود RadioJavan: {str(e)[:200]}")

    loop = asyncio.get_running_loop()
    last_download_error: yt_dlp.utils.DownloadError | None = None

    for profile in _youtube_ydl_profiles(source_url):
        opts = _base_ydl_opts(
            output_template,
            platform=source_url,
            use_cookies=profile["use_cookies"],
            youtube_clients=profile["clients"],
        )
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source_url, download=True)
                return info

        try:
            logger.info("yt-dlp audio attempt: %s", profile["name"])
            info = await loop.run_in_executor(None, _download)
        except yt_dlp.utils.DownloadError as e:
            last_download_error = e
            logger.warning("yt-dlp audio attempt failed (%s): %s", profile["name"], str(e)[:300])
            if _is_youtube_url(source_url):
                continue
            break

        title = info.get("title", "صوت") if info else "صوت"

        # Use request_id to find the specific file, not the newest in dir
        file_path = str(download_dir / f"{request_id}.mp3")
        if not os.path.exists(file_path):
            if _is_youtube_url(source_url):
                continue
            return DownloadResult(success=False, error="فایل صوتی دانلود نشد.")

        file_size = os.path.getsize(file_path)
        if file_size > max_file_size_bytes:
            os.remove(file_path)
            return DownloadResult(
                success=False,
                error=f"فایل بزرگتر از {max_file_size_bytes // (1024*1024)} مگابایت است.",
            )
            
        duration = _extract_audio_duration(file_path)
        return DownloadResult(success=True, file_path=file_path, title=title, duration=duration)

    if last_download_error:
        msg = str(last_download_error)
        m = re.search(r"Unsupported URL: (https?://(?:play\.)?radiojavan\.com[^\s]+)", msg)
        if m:
            return await download_audio(m.group(1), progress_callback)
        return _download_error_result(last_download_error, max_file_size_bytes)

    return DownloadResult(success=False, error="فایل صوتی دانلود نشد.")


def cleanup_file(file_path: str):
    """Remove file after sending."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
