import asyncio
from api_client import fetch_media_from_rapidapi

res = fetch_media_from_rapidapi("https://x.com/panizachi/status/2045128616938242499?s=46&t=b3q51")
print(res)
