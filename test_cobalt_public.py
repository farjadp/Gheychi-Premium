import urllib.request
import json
import sys

url = "https://www.youtube.com/watch?v=tJV-vdbZ388"
cobalt_urls = [
    "https://api.cobalt.q0.wtf/",
    "https://co.eepy.cat/",
    "https://api.cobalt.beparanoid.de/",
    "https://cobalt.api.zcxv.com/"
]

payload = {
    "url": url,
    "alwaysProxy": True
}

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

for c_url in cobalt_urls:
    print(f"Testing {c_url}")
    req = urllib.request.Request(
        c_url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            print("Success:", data.get('status'))
            break
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code)
    except Exception as e:
        print("Error:", str(e))
