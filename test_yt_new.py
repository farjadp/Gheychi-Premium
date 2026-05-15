import urllib.request
import json
import re

video_url = "https://www.youtube.com/watch?v=MkDlnvlJpT0"
vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_url)
video_id = vid_match.group(1)

req = urllib.request.Request(
    f"https://youtube-media-downloader.p.rapidapi.com/v2/video/details?videoId={video_id}",
    headers={
        "X-RapidAPI-Key": "c87faf6a9dmsh0b14ea72f890e09p1e9794jsn0a7724b09dc9",
        "X-RapidAPI-Host": "youtube-media-downloader.p.rapidapi.com"
    },
    method="GET"
)

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
