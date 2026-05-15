import urllib.request
import json
req = urllib.request.Request(
    "https://api.cobalt.tools/api/json",
    data=json.dumps({"url": "https://www.youtube.com/watch?v=MkDlnvlJpT0"}).encode(),
    headers={"Accept": "application/json", "Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req) as res:
        print(res.read().decode())
except Exception as e:
    print(e)
    if hasattr(e, 'read'): print(e.read().decode())
