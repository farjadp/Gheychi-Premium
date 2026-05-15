import urllib.request
import json
import sys

url = "https://cobalt-production-9952.up.railway.app/"
payload = {"url": "https://www.youtube.com/watch?v=tJV-vdbZ388", "alwaysProxy": True}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode('utf-8'),
    headers={"Accept": "application/json", "Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPError:", e.read().decode(), file=sys.stderr)
