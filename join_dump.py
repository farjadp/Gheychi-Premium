import asyncio
import os
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

async def main():
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION_STRING"]
    
    app = Client("dump_joiner", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
    await app.start()
    print("Userbot started...")
    try:
        chat = await app.join_chat("https://t.me/+tzJkU1ABGqk3Yzg0")
        print(f"✅ Joined chat! ID: {chat.id}")
        print(f"Title: {chat.title}")
    except Exception as e:
        print(f"Could not join or already joined: {e}")
        # Try to get it anyway
        try:
            chat = await app.get_chat("https://t.me/+tzJkU1ABGqk3Yzg0")
            print(f"✅ Found chat! ID: {chat.id}")
        except Exception as e2:
            print(f"Could not get chat: {e2}")
    
    await app.stop()

asyncio.run(main())
