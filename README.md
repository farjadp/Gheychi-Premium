# Gheychi Premium

سولوشن شامل دو بخش اصلی است:

- بات تلگرام برای دانلود ویدئو و صدا از YouTube، Instagram، Twitter/X و سایر سایت‌های پشتیبانی‌شده توسط `yt-dlp`
- پنل مدیریت وب برای کنترل محدودیت‌ها، روشن/خاموش کردن دانلود، مدیریت پلتفرم‌های مجاز، مدیریت اشتراک کاربران و مشاهده لاگ‌ها

## ساختار پروژه

- `bot.py`: منطق اصلی بات تلگرام
- `downloader.py`: ارتباط با `yt-dlp` و دانلود فایل
- `admin_panel.py`: پنل مدیریت وب با Flask
- `plans.py`: تعریف پلن‌ها و قوانین هر پکیج
- `runtime_store.py`: ذخیره تنظیمات runtime و لاگ‌ها
- `config.py`: تنظیمات پایه از `.env`
- `data/`: ذخیره تنظیمات و دیتابیس لاگ‌ها
- `downloads/`: فایل‌های موقت دانلودشده

## قابلیت‌ها

- دریافت لینک ویدئو در تلگرام
- نمایش کیفیت‌های قابل دانلود
- دانلود ویدئو یا فقط صدا
- پشتیبانی از YouTube، Instagram، Twitter/X و سرویس‌های دیگر
- محدودیت پویا برای حجم فایل از طریق پنل وب
- امکان غیرفعال کردن کامل دانلود از پنل
- محدود کردن پلتفرم‌های مجاز از پنل
- سیستم پلن و سابسکریپشن برای هر کاربر
- سهمیه‌بندی روزانه، هفتگی و ماهانه بر اساس پلن
- محدودیت مدت ویدئو برای YouTube بر اساس پلن
- دستورهای کاربر مثل `/menu`, `/plans`, `/myplan`, `/usage`, `/mylogs`, `/myid`, `/support`
- ثبت لاگ برای شروع بات، دریافت metadata، خطاها، دانلود موفق و fallbackها

## پیش‌نیازها

- Python 3.11 پیشنهاد می‌شود
- `ffmpeg`

### نصب ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

## نصب

```bash
cd /Users/farjad/Downloads/Work-Studio/gheychi-premium
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## تنظیمات

ابتدا فایل env را بساز:

```bash
cp .env.example .env
```

فیلدهای مهم:

```env
BOT_TOKEN=توکن_بات_تلگرام
DOWNLOAD_DIR=downloads
MAX_FILE_SIZE_MB=50
DATA_DIR=data
ADMIN_PASSWORD=یک_پسورد_برای_پنل
SUPPORT_CONTACT=@gheychi_support
```

توضیح متغیرها:

- `BOT_TOKEN`: توکن بات از BotFather
- `DOWNLOAD_DIR`: مسیر فایل‌های موقت
- `MAX_FILE_SIZE_MB`: مقدار اولیه محدودیت فایل
- `DATA_DIR`: مسیر ذخیره تنظیمات و لاگ‌ها
- `ADMIN_PASSWORD`: پسورد پنل مدیریت. اگر خالی باشد، پنل بدون auth باز می‌شود
- `SUPPORT_CONTACT`: آیدی یا لینک مستقیم پشتیبانی

## اجرای بات

```bash
cd /Users/farjad/Downloads/Work-Studio/gheychi-premium
source .venv/bin/activate
python bot.py
```

## اجرای پنل مدیریت

```bash
cd /Users/farjad/Downloads/Work-Studio/gheychi-premium
source .venv/bin/activate
python admin_panel.py
```

پنل روی این آدرس در دسترس است:

```text
http://127.0.0.1:8080
```

اگر پروژه را روی Railway دیپلوی کرده باشی، پنل مدیریت روی همان دامنه‌ی عمومی سرویس و در ریشه‌ی مسیر `/` باز می‌شود. یعنی آدرس چیزی شبیه `https://<your-service>.up.railway.app/` است، نه یک مسیر جدا.

## API پنل

```text
GET /api/settings
GET /api/logs
GET /api/users
POST /settings
POST /subscriptions
```

## رفتار پنل

از پنل می‌توانی این موارد را تغییر بدهی:

- حداکثر حجم فایل
- فعال/غیرفعال بودن دانلود
- لیست پلتفرم‌های مجاز
- تعریف پلن فعال هر کاربر بر اساس `Telegram User ID`
- تمدید اشتراک به‌صورت ماهانه
- مشاهده مصرف کاربر در پلن فعلی
- مشاهده لاگ خطاها و رویدادها

## پلن‌های اشتراک

### پکیج رایگان

- Twitter/X: `5` لینک در ماه
- Instagram: `5` لینک در ماه

### پکیج استارتر

- RadioJavan: `3` موزیک در ماه
- Twitter/X: `13` لینک در ماه
- Instagram: `13` لینک در روز
- YouTube: `5` لینک در هفته، هر ویدئو زیر `15` دقیقه
- قیمت: `$5` در ماه

### پکیج استاندارد

- RadioJavan: نامحدود
- Twitter/X: نامحدود
- Instagram: نامحدود
- TikTok: `13` ویدئو در ماه
- YouTube: `10` لینک در ماه، هر ویدئو زیر `30` دقیقه
- قیمت: `$13` در ماه

### پکیج حرفه‌ای

- Twitter/X: نامحدود
- Instagram: نامحدود
- TikTok: نامحدود
- Facebook: نامحدود
- Vimeo: نامحدود
- SoundCloud: نامحدود
- YouTube: `10` لینک در ماه، هر ویدئو زیر `60` دقیقه
- قیمت: `$23` در ماه

## جریان فروش دستی اشتراک

در نسخه فعلی، فروش و اعمال اشتراک به‌صورت دستی مدیریت می‌شود:

1. کاربر در بات دستور `/myid` را می‌زند
2. ادمین `Telegram User ID` را از کاربر می‌گیرد
3. ادمین در پنل وب، پلن و تعداد ماه را ثبت می‌کند
4. بات از همان لحظه سهمیه را بر اساس پلن اعمال می‌کند

## ذخیره‌سازی

- تنظیمات runtime در `data/settings.json`
- لاگ‌ها در `data/activity.db`
- کاربران، اشتراک‌ها و مصرف نیز در همان دیتابیس `data/activity.db` ذخیره می‌شوند

## محدودیت‌ها

- محدودیت ارسال فایل بات تلگرام معمولاً 50MB است مگر اینکه از local Bot API server استفاده کنی
- پنل فعلی با Flask development server اجرا می‌شود و برای production بهتر است پشت reverse proxy یا WSGI server قرار بگیرد

## اسناد تکمیلی

- راهنمای استفاده روزمره: `HOWTOUSE.md`
- تاریخچه تغییرات: `CHANGELOG.md`
