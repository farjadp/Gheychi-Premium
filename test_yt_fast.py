import urllib.request
import json
import sys

url = "https://youtube-video-fast-downloader-24-7.p.rapidapi.com/get-video-info/9rRvmcDpWwA?return_available_quality=false&response_mode=default"
req = urllib.request.Request(url, headers={
    "X-RapidAPI-Host": "youtube-video-fast-downloader-24-7.p.rapidapi.com",
    "X-RapidAPI-Key": "c87faf6a9dmsh0b14ea72f890e09p1e9794jsn0a7724b09dc9",
    "User-Agent": "Mozilla/5.0"
})
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTPError {e.code}: {body[:100]}", file=sys.stderr)
except Exception as e:
    print(e, file=sys.stderr)
