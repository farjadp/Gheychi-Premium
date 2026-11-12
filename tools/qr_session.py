"""
qr_session.py — UserBot session via QR login
=============================================
Same output as generate_session.py (a Pyrogram session string), but logs in by
scanning a QR code from an already logged-in phone instead of a login code.
Use it when Telegram withholds the login code.

Run:
    .venv/bin/python tools/qr_session.py

On the phone: Settings → Devices → Link Desktop Device → scan the QR.
Needs TG_API_ID / TG_API_HASH in .env and `pip install qrcode` (local only).
"""

import asyncio
import base64
import getpass
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import qrcode
from pyrogram import Client, raw
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.session import Auth, Session

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
REFRESH_SECONDS = 5


def show_qr(token: bytes) -> None:
    url = "tg://login?token=" + base64.urlsafe_b64encode(token).decode().rstrip("=")
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    print("\033[2J\033[H", end="")  # clear screen so the new QR replaces the old one
    print("Phone → Settings → Devices → Link Desktop Device → scan:\n")
    qr.print_ascii(invert=True)
    print(f"\nQR refreshes every {REFRESH_SECONDS}s until scanned. Ctrl+C to abort.")


async def switch_dc(client: Client, dc_id: int) -> None:
    """Move the in-memory session to the DC the account lives on (same as Pyrogram's send_code)."""
    await client.session.stop()
    test_mode = await client.storage.test_mode()
    await client.storage.dc_id(dc_id)
    await client.storage.auth_key(await Auth(client, dc_id, test_mode).create())
    client.session = Session(client, dc_id, await client.storage.auth_key(), test_mode)
    await client.session.start()


async def wait_for_scan(client: Client):
    last_token = None
    while True:
        r = await client.invoke(
            raw.functions.auth.ExportLoginToken(api_id=API_ID, api_hash=API_HASH, except_ids=[])
        )
        if isinstance(r, raw.types.auth.LoginToken):
            if r.token != last_token:
                show_qr(r.token)
                last_token = r.token
            await asyncio.sleep(REFRESH_SECONDS)
            continue
        if isinstance(r, raw.types.auth.LoginTokenMigrateTo):
            await switch_dc(client, r.dc_id)
            r = await client.invoke(raw.functions.auth.ImportLoginToken(token=r.token))
        if isinstance(r, raw.types.auth.LoginTokenSuccess):
            return r.authorization
        raise RuntimeError(f"Unexpected response: {type(r).__name__}")


async def main() -> None:
    if not API_ID or not API_HASH:
        sys.exit("❌ TG_API_ID / TG_API_HASH are not set in .env")

    client = Client("qr_login", api_id=API_ID, api_hash=API_HASH, in_memory=True, no_updates=True)
    await client.connect()
    try:
        try:
            auth = await wait_for_scan(client)
            user = auth.user
        except SessionPasswordNeeded:
            print("\n🔑 Two-step verification is on.")
            user = await client.check_password(getpass.getpass("Password: "))

        await client.storage.user_id(user.id)
        await client.storage.is_bot(False)
        session_string = await client.export_session_string()

        print("\033[2J\033[H", end="")
        print(f"✅ Logged in as {user.first_name} (@{user.username}) — id {user.id}\n")
        if (user.username or "").lower() != "farjadtalks":
            print("⚠️  This is NOT @FarjadTalks. Private links will fail with this account.\n")
        print("TG_SESSION_STRING (paste into Railway only — do not save or reuse it locally):\n")
        print(session_string)
    finally:
        # disconnect without log_out: logging out would revoke the session we just made
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
