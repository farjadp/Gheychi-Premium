import asyncio
from api_client import fetch_media_from_rapidapi

res = fetch_media_from_rapidapi("https://x.com/panizachi/status/2045128616938242499")
print(res)
