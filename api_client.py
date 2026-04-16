import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import logging

from runtime_store import load_settings
from config import USE_COBALT_API, COBALT_API_URL, USE_RAPIDAPI, RAPIDAPI_KEY, RAPIDAPI_HOST

logger = logging.getLogger(__name__)

def is_cobalt_supported_url(url: str) -> bool:
    """Check if the URL should be processed by Cobalt API."""
    keywords = ["twitter.com", "x.com", "instagram.com", "tiktok.com", "reddit.com", "pinterest.com"]
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
    """Fallback logic stub for RapidAPI."""
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
        return {"success": False, "error": "تنظیمات RapidAPI تکمیل نشده است."}
    
    # This is a stub for the generic Twitter Video Downloader endpoints on RapidAPI.
    # In practice, endpoints differ based on which specific RapidAPI service is subscribed.
    api_endpoint = f"https://{RAPIDAPI_HOST}/twitter/download"
    req = Request(
        f"{api_endpoint}?url={url}",
        headers={
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        }
    )
    
    try:
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            video_url = data.get("video_url")
            if video_url:
                return {"success": True, "url": video_url, "source": "RapidAPI"}
            return {"success": False, "error": "اطلاعات ویدیو در پاسخ RapidAPI یافت نشد."}
    except Exception as e:
        logger.error(f"RapidAPI Error: {str(e)}")
        return {"success": False, "error": f"خطا در ارتباط با RapidAPI: {str(e)[:100]}"}

def get_direct_media_url(url: str, quality: str = "max") -> dict:
    """Route the request to Cobalt or RapidAPI based on config."""
    settings = load_settings()
    if settings.get("use_cobalt_api", USE_COBALT_API) and is_cobalt_supported_url(url):
        logger.info("Using Cobalt API for URL: %s", url)
        return fetch_media_from_cobalt(url, quality)
        
    return {"success": False, "error": "هیچ واسط دانلودر مستقیمی (API) فعال نیست."}
