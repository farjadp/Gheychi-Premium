"""
Concurrency guards
==================
دو محافظ برای مسیر دانلود:

1. `download_slot()` — سقف سراسری دانلودهای هم‌زمان. بدون این، هر پیام
   مستقیماً یک پروسه‌ی yt-dlp و یک فایل نیمه‌کاره روی دیسک می‌سازد و یک
   دقیقه‌ی شلوغ کانتینر را پر می‌کند.

2. `user_slot()` — هر کاربر در هر لحظه فقط یک دانلود فعال دارد. این
   محافظ نشتی سهمیه را می‌بندد: چک سهمیه قبل از دانلود انجام می‌شود ولی
   ثبت مصرف بعد از ارسال موفق، پس بدون قفل، ده لینکِ هم‌زمان هر ده‌تا از
   یک چکِ «۰ از ۵ مصرف‌شده» رد می‌شوند.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from config import MAX_CONCURRENT_DOWNLOADS

logger = logging.getLogger(__name__)

_global_sem: asyncio.Semaphore | None = None
_user_locks: dict[int, asyncio.Lock] = {}


def _semaphore() -> asyncio.Semaphore:
    # ساخت با تأخیر: Semaphore باید داخل event loop در حال اجرا ساخته شود.
    global _global_sem
    if _global_sem is None:
        _global_sem = asyncio.Semaphore(max(1, MAX_CONCURRENT_DOWNLOADS))
    return _global_sem


def queue_depth() -> int:
    """چند دانلود همین حالا در حال اجراست (برای پیام انتظار به کاربر)."""
    sem = _semaphore()
    return max(0, MAX_CONCURRENT_DOWNLOADS - sem._value)


def is_busy() -> bool:
    """آیا همه‌ی slotها اشغال‌اند؟ برای نمایش پیام «در صف» قبل از انتظار."""
    return _semaphore().locked()


@asynccontextmanager
async def download_slot():
    """یک slot از سقف سراسری می‌گیرد و در پایان آزاد می‌کند."""
    sem = _semaphore()
    await sem.acquire()
    try:
        yield
    finally:
        sem.release()


class UserBusy(Exception):
    """کاربر همین حالا یک دانلود فعال دارد."""


@asynccontextmanager
async def user_slot(user_id: int):
    """
    قفل تک‌نفره‌ی هر کاربر. اگر کاربر دانلود فعالی داشته باشد بلافاصله
    `UserBusy` می‌دهد — منتظر نمی‌ماند، چون هدف رد کردن سیل درخواست است
    نه صف کردن آن.
    """
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = _user_locks[user_id] = asyncio.Lock()

    if lock.locked():
        raise UserBusy

    await lock.acquire()
    try:
        yield
    finally:
        lock.release()
        # جلوگیری از رشد بی‌پایان dict روی بات پرترافیک
        if not lock.locked() and not lock._waiters:
            _user_locks.pop(user_id, None)
