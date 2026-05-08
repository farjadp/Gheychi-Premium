import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import logging

from runtime_store import load_settings
from config import USE_COBALT_API, COBALT_API_URL, USE_RAPIDAPI, RAPIDAPI_KEY, RAPIDAPI_HOST, RAPIDAPI_YT_HOST

logger = logging.getLogger(__name__)

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
    import re
    vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not vid_match:
        return {"success": False, "error": "لینک یوتیوب نامعتبر است."}
        
    video_id = vid_match.group(1)
    api_endpoint = f"https://youtube-video-fast-downloader-24-7.p.rapidapi.com/get-video-info/{video_id}?return_available_quality=false&response_mode=default"
    
    settings = load_settings()
    rapid_key = settings.get("rapidapi_key") or RAPIDAPI_KEY
    if not rapid_key:
        return {"success": False, "error": "کلید RapidAPI تنظیم نشده است."}

    req = Request(
        api_endpoint,
        headers={
            "x-rapidapi-key": rapid_key,
            "x-rapidapi-host": "youtube-video-fast-downloader-24-7.p.rapidapi.com"
        },
        method="GET"
    )

    try:
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            direct_url = None
            if quality == "audio":
                if "audio_url" in data: direct_url = data["audio_url"]
                elif "audioUrl" in data: direct_url = data["audioUrl"]
                elif "audios" in data and isinstance(data["audios"], list) and len(data["audios"]) > 0: direct_url = data["audios"][0].get("url")
            
            if not direct_url:
                if "video_url" in data: direct_url = data["video_url"]
                elif "videoUrl" in data: direct_url = data["videoUrl"]
                elif "url" in data and isinstance(data["url"], str) and data["url"].startswith("http"): direct_url = data["url"]
                elif "videos" in data and isinstance(data["videos"], list) and len(data["videos"]) > 0:
                    videos = data["videos"]
                    good_videos = [v for v in videos if v.get("hasAudio") is not False]
                    if good_videos: direct_url = good_videos[0].get("url")
                    else: direct_url = videos[0].get("url")
                elif "data" in data and isinstance(data["data"], dict):
                    inner = data["data"]
                    if quality == "audio" and "audioUrl" in inner: direct_url = inner["audioUrl"]
                    elif "videoUrl" in inner: direct_url = inner["videoUrl"]
                    elif "url" in inner: direct_url = inner["url"]

            if direct_url:
                return {"success": True, "url": direct_url, "source": "RapidAPI (YouTube Fast)"}
            
            return {"success": False, "error": "فرمت مناسبی برای دانلود یافت نشد."}

    except HTTPError as e:
        return {"success": False, "error": f"خطای ارتباط با سرور یوتیوب ({e.code})"}
    except Exception as e:
        return {"success": False, "error": f"خطا در ارتباط با API جدید: {str(e)[:100]}"}

def get_direct_media_url(url: str, quality: str = "max") -> dict:
    """Route the request to Cobalt or RapidAPI based on config.
    Implements a fallback chain: Cobalt -> RapidAPI. 
    (If both fail, downloader.py falls back to yt-dlp)."""
    settings = load_settings()
    errors = []
    
    url_lower = url.lower()
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    
    # Layer 0: Dedicated Cobalt
    if settings.get("use_cobalt_api", USE_COBALT_API) and is_cobalt_supported_url(url):
        logger.info("Using Cobalt API for URL: %s", url)
        res = fetch_media_from_cobalt(url, quality)
        if res.get("success"):
            return res
        else:
            logger.warning("Cobalt failed: %s", res.get("error"))
            errors.append(res.get("error", "Cobalt Error"))

    # Layer 1: YouTube FAST Downloader (only for youtube)
    if is_youtube:
        logger.info("Using YouTube FAST API for URL: %s", url)
        res = fetch_media_from_youtube_fast_api(url, quality)
        if res.get("success"):
            return res
        else:
            logger.warning("YouTube FAST API failed: %s", res.get("error"))
            errors.append(res.get("error", "YouTube FAST API Error"))
            
    # Layer 2: RapidAPI
    rapid_key = settings.get("rapidapi_key") or RAPIDAPI_KEY
    if rapid_key:
        logger.info("Using RapidAPI for URL: %s", url)
        res = fetch_media_from_rapidapi(url)
        if res.get("success"):
            return res
        else:
            logger.warning("RapidAPI failed: %s", res.get("error"))
            errors.append(res.get("error", "RapidAPI Error"))
            
    return {"success": False, "error": " | ".join(errors) if errors else "هیچ واسط دانلودر مستقیمی (API) فعال نیست."}
