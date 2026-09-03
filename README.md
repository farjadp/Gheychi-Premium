# Gheychi Premium

سولوشن شامل سه بخش اصلی است:

- **بات تلگرام** برای دانلود ویدئو و صدا از YouTube، Instagram، Twitter/X و سایر سایت‌های پشتیبانی‌شده توسط `yt-dlp`
- **Save Restricted Content** — دریافت محتوای پروتکت‌شده تلگرام از طریق UserBot (Pyrogram/MTProto)
- **پنل مدیریت وب** برای کنترل محدودیت‌ها، مدیریت پلن‌ها و اشتراک کاربران، تراکنش‌ها و لاگ‌ها — به‌همراه وب‌سایت معرفی و داشبورد کاربر

## ساختار پروژه

- `main.py`: entrypoint پروداکشن — بات، پنل و auto-updater را به‌صورت سه پروسه اجرا می‌کند
- `bot.py`: منطق اصلی بات تلگرام
- `downloader.py`: ارتباط با `yt-dlp` و دانلود فایل
- `api_client.py`: لایه API خارجی (Cobalt / RapidAPI)
- `userbot_client.py`: کلاینت Pyrogram برای محتوای restricted تلگرام
- `tg_link_handler.py`: هندلر مجزای لینک‌های `t.me`
- `admin_panel.py`: پنل مدیریت وب با Flask
- `plans.py`: تعریف پلن‌ها و قوانین هر پکیج
- `runtime_store.py`: ذخیره تنظیمات runtime، لاگ‌ها، کاربران و تراکنش‌ها
- `locales.py`: متن‌های دوزبانه فارسی/انگلیسی
- `config.py`: تنظیمات پایه از `.env`
- `website/`: صفحات استاتیک و داشبورد کاربر
- `data/`: تنظیمات، پلن‌ها و دیتابیس SQLite
- `downloads/`: فایل‌های موقت دانلودشده

## قابلیت‌ها

### دانلود عمومی

- دریافت لینک ویدئو در تلگرام و نمایش کیفیت‌های قابل دانلود
- دانلود ویدئو یا فقط صدا (MP3)
- پشتیبانی از YouTube، Instagram، Twitter/X، TikTok، Reddit و بیش از ۱۰۰۰ سایت دیگر
- **معماری چندلایه دانلود** — برای لینک‌های غیریوتیوبی که Cobalt پشتیبانی می‌کند ابتدا API امتحان می‌شود و در صورت شکست `yt-dlp` وارد می‌شود؛ برای YouTube مسیر برعکس است، چون URLهای امضاشدهٔ API روی سرور اغلب ۴۰۳ می‌گیرند
- پشتیبانی از کوکی مجزا برای هر پلتفرم (فایل مستقیم یا base64 در متغیر محیطی)

### Save Restricted Content

- دریافت پیام‌های پروتکت‌شده از کانال‌ها و گروه‌های خصوصی با اکانت شخصی
- پشتیبانی از لینک `t.me/username/123` و `t.me/c/<id>/<msg>` به‌همراه topicها
- دانلود آلبوم (media group) به‌صورت کامل
- عبور از محدودیت ۵۰ مگابایتی Bot API با آپلود واسطه در dump channel *(نیازمند `DUMP_CHANNEL_ID`)*

### اشتراک و مدیریت

- سیستم پلن و سابسکریپشن برای هر کاربر با سهمیه‌بندی روزانه، هفتگی و ماهانه
- محدودیت مدت ویدئو بر اساس پلن و پلتفرم
- محدودیت پویا برای حجم فایل و امکان غیرفعال کردن کامل دانلود از پنل
- رابط کاربری دوزبانه فارسی/انگلیسی
- دستورهای کاربر: `/menu`, `/plans`, `/myplan`, `/usage`, `/mylogs`, `/myid`, `/support`, `/lang`, `/dashboard`
- ثبت لاگ برای شروع بات، دریافت metadata، خطاها، دانلود موفق و fallbackها

## پیش‌نیازها

- Python 3.11 پیشنهاد می‌شود
- `ffmpeg`
- `Node.js` (برای PO-Token provider یوتیوب)

### نصب ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

## نصب

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## تنظیمات

ابتدا فایل env را بساز:

```bash
cp .env.example .env
```

### متغیرهای ضروری

```env
BOT_TOKEN=توکن_بات_تلگرام
ADMIN_PASSWORD=یک_پسورد_برای_پنل
DATA_DIR=data
DOWNLOAD_DIR=downloads
MAX_FILE_SIZE_MB=50
SUPPORT_CONTACT=@gheychi_support
BASE_URL=https://your-domain.com
FLASK_SECRET_KEY=یک_رشته_تصادفی_قوی
```

- `BOT_TOKEN`: توکن بات از BotFather
- `ADMIN_PASSWORD`: پسورد پنل مدیریت. **اگر خالی باشد پنل اصلاً بالا نمی‌آید** و پروسه با خطا خارج می‌شود
- `DATA_DIR`: مسیر ذخیره تنظیمات و دیتابیس. روی Railway باید به mount path همان volume اشاره کند (`/data`)، وگرنه دیتا با هر deploy پاک می‌شود
- `BASE_URL`: دامنهٔ عمومی. مبنای ساخت magic linkهای داشبورد کاربر است؛ اگر ست نشود لینک‌ها به `127.0.0.1` اشاره می‌کنند
- `FLASK_SECRET_KEY`: کلید امضای magic link. **حتماً ست کن** — در غیر این صورت یک مقدار fallback ثابت و عمومی استفاده می‌شود و لینک‌ها قابل جعل‌اند

### Save Restricted Content

```env
TG_API_ID=از_my.telegram.org
TG_API_HASH=از_my.telegram.org
TG_SESSION_STRING=خروجی_generate_session.py
DUMP_CHANNEL_ID=-100xxxxxxxxxx
```

- session string را یک‌بار با `python generate_session.py` بساز
- `DUMP_CHANNEL_ID`: کانال واسطه برای فایل‌های بالای ۵۰ مگابایت. **بات هم باید عضو این کانال باشد**، وگرنه `copy_message` شکست می‌خورد. بدون این متغیر هر فایل بزرگ‌تر از ۵۰MB رد می‌شود

### لایه‌های API (اختیاری)

```env
USE_COBALT_API=True
COBALT_API_URL=https://your-cobalt-instance/
COBALT_API_JWT=

USE_RAPIDAPI=False
RAPIDAPI_KEY=
RAPIDAPI_HOST=auto-download-all-in-one.p.rapidapi.com
RAPIDAPI_YT_HOST=youtube-info-download-api.p.rapidapi.com
```

### پرداخت (اختیاری)

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

کلید Stripe از تنظیمات runtime خوانده می‌شود؛ می‌توانی آن را از پنل مدیریت هم ست کنی. تا وقتی ست نشود دکمهٔ خرید به کاربر پیام «پیکربندی نشده» می‌دهد و تنها مسیر فعال، تأیید دستی تراکنش از پنل است.

### کوکی‌ها (اختیاری ولی توصیه‌شده)

برای YouTube و Instagram روی سرور معمولاً بدون کوکی به bot-check می‌خوری. دو راه:

```env
# مسیر مستقیم فایل
COOKIES_YOUTUBE=data/cookies_youtube.txt

# یا base64، که هنگام startup توسط main.py دیکد و روی دیسک نوشته می‌شود
COOKIES_YOUTUBE_B64=<base64>
```

## اجرا

### پروداکشن (هر دو پروسه با هم)

```bash
source .venv/bin/activate
python main.py
```

### توسعه (جداگانه)

```bash
source .venv/bin/activate
python bot.py
```

```bash
source .venv/bin/activate
python admin_panel.py
```

پنل روی پورت `8080` بالا می‌آید (یا هر مقداری که در `PORT` ست شده باشد) و با gunicorn سرو می‌شود:

```text
http://127.0.0.1:8080
```

روی Railway پنل مدیریت روی همان دامنه‌ی عمومی سرویس و در ریشه‌ی مسیر `/` باز می‌شود.

## API پنل

```text
GET  /api/settings
GET  /api/logs
GET  /api/users
POST /settings
POST /subscriptions
POST /webhook/stripe
GET  /auth/magic
GET  /dashboard
```

## رفتار پنل

از پنل می‌توانی این موارد را تغییر بدهی:

- حداکثر حجم فایل و فعال/غیرفعال بودن دانلود
- لیست پلتفرم‌های مجاز
- تعریف و ویرایش پلن‌ها (پلتفرم، لیمیت، قیمت، حداکثر مدت)
- تخصیص و تمدید اشتراک بر اساس `Telegram User ID`
- مشاهده مصرف کاربر، لاگ رویدادها و آمار تحلیلی ۳۰ روزه
- ارسال پیام همگانی (broadcast)
- تأیید دستی تراکنش‌ها
- دانلود بکاپ دیتابیس

## پلن‌های اشتراک (کاملاً داینامیک)

**هیچ پکیجی در کدهای بات hardcode نشده است.** تمام پلتفرم‌ها، لیمیت‌ها و قیمت‌ها از `data/plans.json` خوانده می‌شوند و از تبِ پلن‌ها در پنل قابل ویرایش‌اند:

- ایجاد پلتفرم‌های جدید یا تغییر قیمت بسته‌ها
- تخصیص محدودیت روزانه، هفتگی و ماهانه برای هر شبکه اجتماعی
- تعیین حداکثر مدت مجاز دانلود برای هر پلتفرم

## جریان فروش (Stripe)

1. کاربر در بات دستور `/plans` را می‌زند
2. روی دکمه‌ی اختصاصیِ یک پکیج کلیک می‌کند
3. یک Stripe Checkout Session مجزا برای آن کاربر صادر می‌شود
4. کاربر با دکمه‌ی «انتقال به درگاه پرداخت» پرداخت را انجام می‌دهد
5. وب‌هوک روی `admin_panel.py` پرداخت را می‌خواند و اکانت را برای ۳۰ روز شارژ می‌کند

*نکته:* تمدید دستی از داشبورد ادمین همیشه در دسترس است و در نبود کلید Stripe تنها مسیر فعال است.

## ذخیره‌سازی و پشتیبان‌گیری

- تنظیمات runtime در `data/settings.json`
- پکیج‌ها در `data/plans.json`
- کاربران، لاگ‌ها، مصرف و تراکنش‌ها در `data/activity.db` (SQLite)
- ادمین می‌تواند از پنل، بکاپ کامل را در هر لحظه دانلود کند

روی Railway این مسیر باید روی یک volume باشد. سرویس `Gheychi-Premium` در پروژه‌ی `devoted-upliftment` یک volume روی `/data` دارد و `DATA_DIR` به همان اشاره می‌کند.

## محدودیت‌ها

- محدودیت ارسال فایل Bot API معمولاً ۵۰MB است. برای عبور از آن یا dump channel را پیکربندی کن یا از local Bot API server استفاده کن
- لینک‌های invite تلگرام (`t.me/+hash`) پشتیبانی نمی‌شوند
- RadioJavan فقط صوت — ویدئو رد می‌شود
- هیچ سقفی روی تعداد دانلودهای هم‌زمان وجود ندارد؛ زیر بار سنگین ممکن است حافظه و دیسک پر شود
- `main.py` هر ۱۲ ساعت `yt-dlp` را در runtime آپدیت می‌کند. روی فایل‌سیستم ephemeral این کار با هر restart تکرار می‌شود

## اسناد تکمیلی

- راهنمای استفاده روزمره: `HOWTOUSE.md`
- تاریخچه تغییرات: `CHANGELOG.md`
