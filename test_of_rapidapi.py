import urllib.request
import json
import ssl

username = "ellasutton"
req = urllib.request.Request(
    f"https://onlyfans-profile-scraper2.p.rapidapi.com/posts/{username}",
    headers={
        "X-RapidAPI-Key": "c87faf6a9dmsh0b14ea72f890e09p1e9794jsn0a7724b09dc9",
        "X-RapidAPI-Host": "onlyfans-profile-scraper2.p.rapidapi.com"
    },
    method="GET"
)

try:
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=context) as response:
        data = json.loads(response.read().decode('utf-8'))
        # Dump the first post with media to see structure
        if "list" in data and len(data["list"]) > 0:
            for p in data["list"]:
                if p.get("media") and len(p["media"]) > 0:
                    print(json.dumps(p, indent=2))
                    break
        else:
            print("No posts found or list is empty")
            print(json.dumps(data)[:1000])
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
