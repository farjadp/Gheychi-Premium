import asyncio
from api_client import get_direct_media_url
import os

os.environ["USE_COBALT_API"] = "True"
os.environ["COBALT_API_URL"] = "https://cobalt-production-9952.up.railway.app/"

url = "https://www.youtube.com/watch?v=tJV-vdbZ388"
res = get_direct_media_url(url, "max")
print(res)
