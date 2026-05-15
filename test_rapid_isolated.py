import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

def fetch_media_from_rapidapi(url: str, rapid_key: str, rapid_host: str) -> dict:
    api_endpoint = f"https://{rapid_host}/v1/social/autolink"
    payload = {"url": url}
    
    req = Request(
        api_endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "X-RapidAPI-Key": rapid_key,
            "X-RapidAPI-Host": rapid_host,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        method="POST"
    )
    
    try:
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
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
            
            if direct_url:
                return {"success": True, "url": direct_url, "source": "RapidAPI"}
                
            return {"success": False, "error": f"لینک دانلود مستقیم یافت نشد."}
            
    except Exception as e:
        return {"success": False, "error": f"Error: {e}"}

print(fetch_media_from_rapidapi("https://x.com/panizachi/status/2045128616938242499?s=46&t=b3q51", "c87faf6a9dmsh0b14ea72f890e09p1e9794jsn0a7724b09dc9", "auto-download-all-in-one.p.rapidapi.com"))
