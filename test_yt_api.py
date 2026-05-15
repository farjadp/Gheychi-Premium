import asyncio
from api_client import fetch_media_from_youtube_fast_api, fetch_media_from_rapidapi
import urllib.request
import os

url = "https://www.youtube.com/watch?v=tJV-vdbZ388"
res1 = fetch_media_from_youtube_fast_api(url, "max")
print("FAST API Result:", res1)

if res1.get("success"):
    direct_url = res1["url"]
    print(f"Testing FAST API URL: {direct_url[:50]}...")
    req = urllib.request.Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(req)
        print("FAST API direct URL works!")
    except Exception as e:
        print(f"FAST API direct URL failed: {e}")

print("---------------------------------")
res2 = fetch_media_from_rapidapi(url)
print("RapidAPI Result:", res2)

if res2.get("success"):
    direct_url = res2["url"]
    print(f"Testing RapidAPI URL: {direct_url[:50]}...")
    req = urllib.request.Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(req)
        print("RapidAPI direct URL works!")
    except Exception as e:
        print(f"RapidAPI direct URL failed: {e}")
