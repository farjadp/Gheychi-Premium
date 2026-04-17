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
        
    payload = {
        "url": url,
        "vQuality": quality if quality != "audio" else "max",
        "isAudioOnly": quality == "audio"
    }

    req = Request(
        api_endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },
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
        return {"success": False, "error": "مسیر مستقیم RapidAPI برای یوتیوب فعال نیست (محدودیت IP گوگل). ارسال به لایه بعدی..."}
    
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

def get_direct_media_url(url: str, quality: str = "max") -> dict:
    """Route the request to Cobalt or RapidAPI based on config.
    Implements a fallback chain: Cobalt -> RapidAPI. 
    (If both fail, downloader.py falls back to yt-dlp)."""
    settings = load_settings()
    errors = []
    
    # Layer 1: Cobalt
    if settings.get("use_cobalt_api", USE_COBALT_API) and is_cobalt_supported_url(url):
        logger.info("Using Cobalt API for URL: %s", url)
        res = fetch_media_from_cobalt(url, quality)
        if res.get("success"):
            return res
        else:
            logger.warning("Cobalt failed: %s", res.get("error"))
            errors.append(res.get("error", "Cobalt Error"))
            
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
