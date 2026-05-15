import asyncio
from api_client import fetch_media_from_rapidapi
import urllib.request
import os

url = "https://www.youtube.com/watch?v=tJV-vdbZ388"
res2 = fetch_media_from_rapidapi(url)
print("RapidAPI Result:", res2)

if res2.get("success"):
    direct_url = res2["url"]
    print("Testing with basic headers...")
    req1 = urllib.request.Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(req1)
        print("Basic headers work!")
    except Exception as e:
        print(f"Basic headers failed: {e}")
        
    print("Testing with downloader.py headers...")
    headers2 = {
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
    req2 = urllib.request.Request(direct_url, headers=headers2)
    try:
        urllib.request.urlopen(req2)
        print("Complex headers work!")
    except Exception as e:
        print(f"Complex headers failed: {e}")

