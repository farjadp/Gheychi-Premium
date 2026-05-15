import json
from urllib.request import Request, urlopen
import re
from urllib.error import HTTPError

API_TPLS = [
    "https://play.radiojavan.com/api/p/podcast?id={id}",
    "https://play.radiojavan.com/api/podcast?id={id}",
    "https://play.radiojavan.com/api2/podcast?id={id}",
    "https://play.radiojavan.com/api/p/mp3?id={id}"
]

for tpl in API_TPLS:
    url = tpl.format(id="5283")
    print(f"Testing {url} ...")
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req) as resp:
            data = resp.read()
            print("OK:", data[:200])
    except HTTPError as e:
        print("FAIL:", e)

