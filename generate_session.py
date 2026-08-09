"""
generate_session.py — UserBot Session Generator
================================================
این اسکریپت را یکبار به صورت local اجرا کنید تا session string تولید شود.
مقدار session string را در متغیر TG_SESSION_STRING در .env قرار دهید.

اجرا:
    python generate_session.py

پیش‌نیاز:
    - TG_API_ID و TG_API_HASH در .env تنظیم شده باشند
    - pyrogram نصب باشد (pip install pyrogram TgCrypto)
"""

import asyncio
import sys
import os
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")


def check_requirements():
    if not API_ID or not API_HASH:
        print("❌ خطا: TG_API_ID و TG_API_HASH در .env تنظیم نشده‌اند.")
        print("   از https://my.telegram.org اعتبارنامه‌ها را تهیه کنید.")
        sys.exit(1)
    try:
        import pyrogram
    except ImportError:
        print("❌ خطا: pyrogram نصب نیست.")
        print("   اجرا کنید: pip install pyrogram TgCrypto")
        sys.exit(1)


async def generate():
    from pyrogram import Client

    print("\n" + "=" * 55)
    print("  🔐 Gheychi Premium — UserBot Session Generator")
    print("=" * 55)
    print()
    print("⚠️  توجه: یک اکانت جداگانه (dedicated) برای UserBot استفاده کنید.")
    print("   از اکانت اصلی خود استفاده نکنید.\n")

    async with Client(
        name="session_generator_temp",
        api_id=API_ID,
        api_hash=API_HASH,
        in_memory=True,
    ) as client:
        session_string = await client.export_session_string()
        me = await client.get_me()

    print("\n" + "=" * 55)
    print(f"✅ لاگین موفق: {me.first_name} (@{me.username})")
    print("=" * 55)
    print("\n📋 Session String (این مقدار را در .env یا Railway قرار دهید):\n")
    print(f"TG_SESSION_STRING={session_string}")
    print("\n" + "=" * 55)
    print("⚠️  هرگز این رشته را با کسی به اشتراک نگذارید!")
    print("=" * 55 + "\n")

    # نوشتن در فایل session_string.txt برای راحتی
    output_file = Path("session_string.txt")
    output_file.write_text(f"TG_SESSION_STRING={session_string}\n")
    print(f"💾 مقدار در {output_file} هم ذخیره شد.")


if __name__ == "__main__":
    check_requirements()
    asyncio.run(generate())
