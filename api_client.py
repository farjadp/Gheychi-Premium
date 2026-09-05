import json
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import logging

from runtime_store import load_settings
from config import USE_COBALT_API, COBALT_API_URL, USE_RAPIDAPI, RAPIDAPI_KEY, RAPIDAPI_HOST, RAPIDAPI_YT_HOST

logger = logging.getLogger(__name__)

# How long to wait for the YouTube provider to prepare a file. A warm job comes
# back in 14-21 seconds, but a cold one has been seen to pass 60 and then finish
# at 15 on the retry, so the ceiling has room for a slow start rather than
# failing a request that was about to succeed. Overridable without a deploy.
YOUTUBE_API_TIMEOUT = int(os.getenv("YOUTUBE_API_TIMEOUT_SECONDS", "150"))

def is_cobalt_supported_url(url: str) -> bool:
    """Check if the URL should be processed by API layers."""
    keywords = ["twitter.com", "x.com", "instagram.com", "tiktok.com", "reddit.com", "pinterest.com", "youtube.com", "youtu.be"]
    url_lower = url.lower()
    return any(kw in url_lower for kw in keywords)

def fetch_media_from_cobalt(url: str, quality: str = "max") -> dict:
    """
    Fetch media direct URL from Cobalt API.
    Returns:
        dict: {"success": True/False, "url": "direct_url", "error": "error message"}
    """
    settings = load_settings()
    cobalt_url = settings.get("cobalt_api_url", COBALT_API_URL)
    if not cobalt_url:
        return {"success": False, "error": "آدرس دسترسی Cobalt پیکربندی نشده است."}

    api_endpoint = cobalt_url.rstrip('/') + "/"
    if quality not in ["max", "1080", "720", "480", "360", "audio"]:
        quality = "max"
        
    # Cobalt v10 payload format
    payload = {
        "url": url,
        "videoQuality": "1080" if quality in ["1080", "max"] else quality,
        "alwaysProxy": True
    }
    if quality == "audio":
        payload["downloadMode"] = "audio"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    cobalt_jwt = settings.get("cobalt_api_jwt")
    if cobalt_jwt:
        headers["Authorization"] = f"Bearer {cobalt_jwt}"

    req = Request(
        api_endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method="POST"
    )

    try:
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            status = data.get("status")
            if status in ["stream", "redirect"]:
                return {"success": True, "url": data.get("url"), "source": "Cobalt"}
            elif status == "picker":
                # Picker provides multiple choices, grab the best video
                picker_items = data.get("picker", [])
                if picker_items:
                    # just take the first one or filter by video
                    return {"success": True, "url": picker_items[0].get("url"), "source": "Cobalt"}
            elif status == "error":
                err_code = data.get("error", {}).get("code", "Unknown")
                return {"success": False, "error": f"خطای کبالت: {err_code}"}
            
            return {"success": False, "error": "فرمت پاسخ Cobalt نامعتبر است."}
            
    except HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            err_json = json.loads(err_body)
            err_msg = err_json.get("error", {}).get("code", str(e))
        except:
            err_msg = str(e)
        logger.error(f"Cobalt HTTP Error ({e.code}): {err_msg}")
        return {"success": False, "error": f"ارتباط با سرور Cobalt مسدود شده است ({e.code})."}
    except URLError as e:
        logger.error(f"Cobalt Connection Error: {e.reason}")
        return {"success": False, "error": f"خطا در اتصال به شبکه Cobalt: {e.reason}"}
    except Exception as e:
        logger.error(f"Cobalt Unexpected Error: {str(e)}")
        return {"success": False, "error": f"خطای دریافت مستقیم: {str(e)[:100]}"}

def fetch_media_from_rapidapi(url: str) -> dict:
    """Fallback logic for RapidAPI supporting both General Social Media and YouTube specific API."""
    import urllib.parse
    
    settings = load_settings()
    # Support both Env and Admin Panel key
    rapid_key = settings.get("rapidapi_key") or RAPIDAPI_KEY
    rapid_host = RAPIDAPI_HOST
    
    url_lower = url.lower()
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    if is_youtube:
        import re
        # Extract video ID
        vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not vid_match:
            return {"success": False, "error": "لینک یوتیوب نامعتبر است."}
            
        video_id = vid_match.group(1)
        api_endpoint = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
        
        # Support both Env and Admin Panel key
        rapid_key = settings.get("rapidapi_key") or RAPIDAPI_KEY
        if not rapid_key:
            return {"success": False, "error": "کلید RapidAPI تنظیم نشده است."}
            
        url_with_params = f"{api_endpoint}?videoId={video_id}"
        req = Request(
            url_with_params,
            headers={
                "X-RapidAPI-Key": rapid_key,
                "X-RapidAPI-Host": "youtube-media-downloader.p.rapidapi.com"
            },
            method="GET"
        )
        try:
            with urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # Find best video format with audio
                best_url = None
                items = data.get("videos", {}).get("items", [])
                
                # Filter to MP4 and hasAudio if possible
                audio_video_items = [i for i in items if i.get("hasAudio") is True and i.get("extension") == "mp4"]
                
                if audio_video_items:
                    # Sort by height descending
                    audio_video_items.sort(key=lambda x: x.get("height", 0), reverse=True)
                    best_url = audio_video_items[0].get("url")
                elif items:
                    # Fallback to any best video
                    items.sort(key=lambda x: x.get("height", 0), reverse=True)
                    best_url = items[0].get("url")
                    
                if best_url:
                    return {"success": True, "url": best_url, "source": "RapidAPI (YouTube)"}
                
                return {"success": False, "error": "فرمت مناسبی برای دانلود یوتیوب یافت نشد."}
        except HTTPError as e:
            return {"success": False, "error": f"خطای YouTube API: {e.code}"}
        except Exception as e:
            logger.error(f"RapidAPI YT Error: {str(e)}")
            return {"success": False, "error": f"خطا در ارتباط با سرور یوتیوب: {str(e)[:100]}"}
    
    if not rapid_key or not rapid_host:
        return {"success": False, "error": "تنظیمات RapidAPI تکمیل نشده است."}
    
    api_endpoint = f"https://{rapid_host}/v1/social/autolink"
    payload = {"url": url}
    
    req = Request(
        api_endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "X-RapidAPI-Key": rapid_key,
            "X-RapidAPI-Host": rapid_host,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
        method="POST"
    )
    
    try:
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            # Smart parsing logic since exact response structure can vary
            direct_url = None
            
            if isinstance(data, dict):
                # Try common paths
                if "medias" in data and isinstance(data["medias"], list) and len(data["medias"]) > 0:
                    direct_url = data["medias"][0].get("url")
                elif "data" in data and isinstance(data["data"], dict):
                    if "video" in data["data"]: direct_url = data["data"]["video"]
                    elif "url" in data["data"]: direct_url = data["data"]["url"]
                elif "video" in data and isinstance(data["video"], str):
                    direct_url = data["video"]
                elif "url" in data and isinstance(data["url"], str) and data["url"].startswith("http"):
                    # Only use "url" if it's not the original source url
                    if data["url"].lower() != url.lower():
                        direct_url = data["url"]

            # Security check: Ensure direct_url is not just the original twitter page again!
            if direct_url and ("x.com/" in direct_url or "twitter.com/" in direct_url) and "video.twimg.com" not in direct_url:
                direct_url = None

            if direct_url:
                return {"success": True, "url": direct_url, "source": "RapidAPI"}
                
            return {"success": False, "error": f"لینک دانلود مستقیم در پاسخ نهایی RapidAPI یافت نشد: {str(data)[:100]}"}
            
    except HTTPError as e:
        err_body = e.read().decode('utf-8')
        return {"success": False, "error": f"خطای {e.code} RapidAPI: {err_body[:100]}"}
    except Exception as e:
        logger.error(f"RapidAPI Error: {str(e)}")
        return {"success": False, "error": f"خطا در ارتباط با RapidAPI: {str(e)[:100]}"}

def fetch_media_from_youtube_fast_api(url: str, quality: str) -> dict:
    """
    Last resort for YouTube, reached only after every yt-dlp profile has failed.

    The provider does the YouTube fetch on its own infrastructure and hands back
    a file on its CDN, so the URL carries no `ip` parameter and is not bound to
    whoever requested it — which is why this works from a datacenter address
    where a googlevideo URL would not.

    It is a two-step API: the first call queues a job, then its progress
    endpoint is polled until the download URL appears. Measured at 14-21s.
    """
    import time
    import urllib.parse

    settings = load_settings()
    rapid_key = settings.get("rapidapi_key") or RAPIDAPI_KEY
    if not rapid_key:
        return {"success": False, "error": "کلید RapidAPI تنظیم نشده است."}

    host = (RAPIDAPI_YT_HOST or "").strip()
    if not host:
        return {"success": False, "error": "RAPIDAPI_YT_HOST تنظیم نشده است."}

    # The provider names formats by height, plus mp3 for audio. When no height
    # was asked for, 360 is the default rather than 720: everything here has to
    # fit inside Telegram's 50 MB bot upload limit, and 720 puts most videos
    # over it. A ten-minute clip is about 27 MB at 360.
    if quality == "audio":
        fmt = "mp3"
    elif str(quality).isdigit():
        fmt = str(quality)
    else:
        fmt = "360"

    quoted = urllib.parse.quote(url, safe="")
    job_url = f"https://{host}/ajax/download.php?format={fmt}&url={quoted}"

    try:
        req = Request(job_url, headers={
            "x-rapidapi-key": rapid_key,
            "x-rapidapi-host": host,
        })
        with urlopen(req, timeout=30) as response:
            remaining = response.headers.get("X-RateLimit-Units-Remaining")
            job = json.loads(response.read().decode("utf-8"))

        if remaining is not None:
            # Roughly four units a request against a daily allowance, so this is
            # the number to watch before YouTube starts failing on quota alone.
            logger.info("YouTube API units remaining: %s", remaining)

        progress_url = job.get("progress_url")
        if not progress_url:
            return {"success": False, "error": f"پاسخ API فاقد progress_url بود: {str(job)[:120]}"}

        deadline = time.monotonic() + YOUTUBE_API_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(2)
            with urlopen(Request(progress_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as pr:
                progress = json.loads(pr.read().decode("utf-8"))
            direct_url = progress.get("download_url")
            if direct_url:
                return {"success": True, "url": direct_url, "source": "RapidAPI (YouTube)"}
            if progress.get("success") == 0 and str(progress.get("text", "")).lower().startswith("error"):
                return {"success": False, "error": f"API یوتیوب خطا داد: {str(progress.get('text'))[:100]}"}

        return {"success": False, "error": f"آماده‌سازی لینک یوتیوب بیش از {YOUTUBE_API_TIMEOUT} ثانیه طول کشید."}

    except HTTPError as e:
        return {"success": False, "error": f"خطای ارتباط با سرور یوتیوب ({e.code})"}
    except Exception as e:
        return {"success": False, "error": f"خطا در ارتباط با API یوتیوب: {str(e)[:100]}"}


def get_direct_media_url(url: str, quality: str = "max") -> dict:
    """Route the request to Cobalt or RapidAPI based on config.
    Implements a fallback chain: Cobalt -> RapidAPI. 
    (If both fail, downloader.py falls back to yt-dlp)."""
    settings = load_settings()
    errors = []
    
    url_lower = url.lower()
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    
    # Layer 0: Dedicated Cobalt
    # The environment variable is a hard off switch: the admin panel stores its own
    # copy of this flag, so flipping the variable alone would be overridden by a
    # stale "true" in the database. Both have to agree before Cobalt is tried.
    if USE_COBALT_API and settings.get("use_cobalt_api", USE_COBALT_API) and is_cobalt_supported_url(url):
        logger.info("Using Cobalt API for URL: %s", url)
        res = fetch_media_from_cobalt(url, quality)
        if res.get("success"):
            return res
        else:
            logger.warning("Cobalt failed: %s", res.get("error"))
            errors.append(res.get("error", "Cobalt Error"))

    rapid_key = settings.get("rapidapi_key") or RAPIDAPI_KEY

    # Layer 1: the YouTube provider, and only for YouTube.
    #
    # It goes ahead of the generic handler because that one answers a YouTube
    # link with a raw googlevideo URL, which is signed against the requesting
    # IP. It reports success, so it used to end the chain here, and the download
    # that followed died with 403 from a datacenter address. This provider
    # fetches on its own infrastructure and returns a file on its CDN, with no
    # such binding.
    if is_youtube and rapid_key:
        logger.info("Using YouTube provider for URL: %s", url)
        res = fetch_media_from_youtube_fast_api(url, quality)
        if res.get("success"):
            return res
        else:
            logger.warning("YouTube provider failed: %s", res.get("error"))
            errors.append(res.get("error", "YouTube API Error"))

    # Layer 2: the generic handler, unchanged for every other platform.
    if rapid_key:
        logger.info("Using RapidAPI for URL: %s", url)
        res = fetch_media_from_rapidapi(url)
        if res.get("success"):
            return res
        else:
            logger.warning("RapidAPI failed: %s", res.get("error"))
            errors.append(res.get("error", "RapidAPI Error"))
            
    return {"success": False, "error": " | ".join(errors) if errors else "هیچ واسط دانلودر مستقیمی (API) فعال نیست."}
