# Changelog

## 2026-04-15

### Added

- اضافه شدن پنل مدیریت وب با `Flask`
- اضافه شدن storage مستقل برای تنظیمات runtime و لاگ‌ها در `runtime_store.py`
- اضافه شدن APIهای `GET /api/settings` و `GET /api/logs`
- اضافه شدن `.gitignore` برای `data/`, `.venv/`, `.env`, `downloads/`
- اضافه شدن مستندات کامل برای setup و استفاده
- اضافه شدن سیستم سابسکریپشن با پلن‌های `free`, `starter`, `standard`, `pro`
- اضافه شدن جدول کاربران، اشتراک‌ها و usage events در SQLite
- اضافه شدن API `GET /api/users`
- اضافه شدن دستورهای `/plans`, `/myplan`, `/usage`, `/myid`
- اضافه شدن دستورهای `/menu`, `/mylogs`, `/support` و ثبت command list رسمی برای تلگرام
- اضافه شدن مدیریت دستی اشتراک کاربران از داخل پنل وب

### Changed

- مهاجرت محیط اجرا به `Python 3.11` و `.venv`
- به‌روزرسانی `yt-dlp` به `2026.3.17`
- تغییر نام فایل‌های موقت دانلود به شناسه کوتاه و یکتا برای حذف خطای `File name too long`
- تغییر wiring دکمه‌های کیفیت از URL مستقیم به token داخلی برای حذف `Button_data_invalid`
- خواندن محدودیت حجم فایل از تنظیمات runtime به‌جای ثابت بودن در startup
- کاهش نویز لاگ‌های `httpx`
- اعمال محدودیت پلتفرم، سهمیه و مدت ویدئو بر اساس پلن فعال کاربر
- پشتیبانی از RadioJavan MP3 از طریق endpoint اختصاصی `play.radiojavan.com/api/p/mp3`

### Fixed

- رفع خطای `Unknown format code 'd' for object of type 'float'` در فرمت‌کردن duration
- رفع `409 Conflict` ناشی از اجرای هم‌زمان چند instance
- رفع مشکل event loop در `progress_hook`
- رفع اثر config خارجی `yt-dlp` با `ignoreconfig=True`
- رفع مشکل YouTube با آپدیت extractor
- رفع خطای طول زیاد نام فایل در macOS
- رفع خطای `Button_data_invalid` برای لینک‌های طولانی Instagram
- رفع نبودن مدل اشتراک و سهمیه برای فروش پلن ماهانه

### Current State

- Twitter/X کار می‌کند
- Instagram کار می‌کند
- YouTube با نسخه جدید `yt-dlp` کار می‌کند
- RadioJavan MP3 کار می‌کند
- پنل مدیریت وب برای کنترل محدودیت‌ها، مشاهده لاگ‌ها و مدیریت اشتراک کاربران فعال است
