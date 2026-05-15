import asyncio
from downloader import download_video

async def main():
    res = await download_video("https://x.com/panizachi/status/2045128616938242499?s=46&t=b3q5", "best")
    print(res)

asyncio.run(main())
