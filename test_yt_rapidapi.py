import urllib.request
import json
import ssl

url = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # me at the zoo
encoded_url = urllib.parse.quote(url)
req = urllib.request.Request(
    f"https://youtube-info-download-api.p.rapidapi.com/ajax/download.php?format=mp4&add_info=0&url={encoded_url}",
    headers={
        "X-RapidAPI-Key": "c87faf6a9dmsh0b14ea72f890e09p1e9794jsn0a7724b09dc9",
        "X-RapidAPI-Host": "youtube-info-download-api.p.rapidapi.com"
    },
    method="GET"
)

try:
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=context) as response:
        print(response.read().decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
