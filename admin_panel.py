"""
داشبورد مدیریت و سرور گرافیکی وب (Flask Web Server)
ایمن‌سازی صفحات، بررسی نشست‌ها و رابط کاربری پنل ادمین جهت کنترل کامل بات از اینجا فرمان‌دهی می‌شود.
"""
import os
import tempfile
import zipfile
import time
from functools import wraps
import asyncio
import threading
from telegram import Bot
import stripe
from config import STRIPE_WEBHOOK_SECRET, BOT_TOKEN

from flask import Flask, Response, jsonify, send_file, redirect, render_template_string, request, url_for, session, abort

from config import ADMIN_PASSWORD, ALLOWED_PLATFORMS
from plans import format_rule, list_plans
from runtime_store import (
    add_log,
    assign_user_plan,
    get_usage_snapshot,
    init_logs_db,
    list_bot_users,
    count_bot_users,
    list_logs,
    get_dashboard_stats,
    load_settings,
    save_settings,
    list_transactions,
    get_transaction,
    update_transaction_status,
    get_financial_stats,
    get_analytics_stats,
)

app = Flask(__name__)
# Security configs
import secrets
from datetime import timedelta
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(24))
app.permanent_session_lifetime = timedelta(hours=8)

# Brute force tracking: { "ip": { "attempts": int, "blocked_until": float } }
login_attempts = {}

@app.before_request
def csrf_protect():
    if request.method == "POST" and request.endpoint not in ["login", "stripe_webhook"]:
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            add_log("WARNING", "csrf_blocked", f"CSRF Blocked for {request.remote_addr} on {request.endpoint}", metadata={"source": "پنل ادمین"})
            return "موجودی فرم نامعتبر است (خطای امنیتی CSRF). صفحه را ریفرش کنید.", 403


def _load_template() -> str:
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


PAGE_TEMPLATE = _load_template()


def flag_map(lang_code):
    if not lang_code: return ""
    code = lang_code.lower()[:2]
    # Simple mapping
    flags = {
        'fa': '🇮🇷', 'en': '🇺🇸', 'ar': '🇸🇦', 'ru': '🇷🇺', 'tr': '🇹🇷',
        'es': '🇪🇸', 'fr': '🇫🇷', 'de': '🇩🇪', 'it': '🇮🇹', 'zh': '🇨🇳',
        'ja': '🇯🇵', 'ko': '🇰🇷', 'hi': '🇮🇳', 'pt': '🇵🇹', 'nl': '🇳🇱'
    }
    return flags.get(code, f"🌍({code})")


def _requires_auth(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return handler(*args, **kwargs)

    return wrapped

@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr
    now = time.time()
    
    # Check brute force block
    if ip in login_attempts:
        if login_attempts[ip]["blocked_until"] > now:
            return "Too many failed attempts. Try again later.", 429
        elif login_attempts[ip]["blocked_until"] <= now:
            # Block expired
            login_attempts[ip] = {"attempts": 0, "blocked_until": 0}
            
    if request.method == "GET":
        return render_template_string(LOGIN_TEMPLATE)

    # Validate login
    password = request.form.get("password", "")
    if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
        session.permanent = True
        session["logged_in"] = True
        session["csrf_token"] = secrets.token_hex(16)
        if ip in login_attempts:
            login_attempts[ip]["attempts"] = 0
            
        add_log("INFO", "admin_login", f"ورود موفق ادمین از {ip}", metadata={"source": "پنل ادمین"})
        return redirect(url_for("admin_index"))
    else:
        # Register failed attempt
        if ip not in login_attempts:
            login_attempts[ip] = {"attempts": 0, "blocked_until": 0}
            
        login_attempts[ip]["attempts"] += 1
        if login_attempts[ip]["attempts"] >= 5:
            # Block for 15 minutes
            login_attempts[ip]["blocked_until"] = now + 900
            add_log("WARNING", "brute_force_blocked", f"مسدودسازی 15 دقیقه‌ای به دلیل لاگین‌های ناموفق. آدرس: {ip}", metadata={"source": "پنل ادمین"})
        else:
            add_log("WARNING", "failed_login", f"تلاش ناموفق برای ورود. آدرس: {ip}", metadata={"source": "پنل ادمین"})
            
        return render_template_string(LOGIN_TEMPLATE, error="رمز عبور اشتباه است.")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/set_lang/<lang_code>")
@_requires_auth
def set_lang(lang_code):
    if lang_code in ["en", "fa"]:
        session["admin_lang"] = lang_code
    return redirect(url_for("admin_index"))

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Control Room Login</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700;800;900&family=Azeret+Mono:wght@400;500;700&display=swap');
    :root {
      --sand: #f6efe3;
      --sand-deep: #eadfcb;
      --ink: #1d1a17;
      --muted: #6d655c;
      --brand: #e76f51;
      --accent: #2a9d8f;
      --gold: #e9c46a;
      --line: rgba(50, 37, 28, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: 'Vazirmatn', sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      background:
        radial-gradient(circle at top left, rgba(233, 196, 106, 0.34), transparent 24%),
        radial-gradient(circle at bottom right, rgba(42, 157, 143, 0.18), transparent 22%),
        linear-gradient(135deg, #f8f2e7 0%, #efe3d1 100%);
      padding: 20px;
    }
    .shell {
      width: min(980px, 100%);
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      background: rgba(255, 249, 241, 0.82);
      border: 1px solid var(--line);
      border-radius: 34px;
      overflow: hidden;
      box-shadow: 0 28px 70px rgba(83, 56, 33, 0.14);
      backdrop-filter: blur(18px);
    }
    .panel {
      padding: 42px;
    }
    .story {
      background: linear-gradient(180deg, rgba(33, 27, 22, 0.96), rgba(50, 38, 30, 0.92));
      color: #fff8ef;
      position: relative;
    }
    .story::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at top right, rgba(231, 111, 81, 0.28), transparent 24%),
        radial-gradient(circle at bottom left, rgba(42, 157, 143, 0.18), transparent 22%);
    }
    .story > * { position: relative; z-index: 1; }
    .badge {
      width: 58px;
      height: 58px;
      border-radius: 18px;
      background: linear-gradient(135deg, var(--gold), var(--brand));
      display: grid;
      place-items: center;
      font-size: 28px;
      color: #241711;
      margin-bottom: 22px;
      box-shadow: 0 16px 30px rgba(0, 0, 0, 0.2);
    }
    .kicker {
      font-family: 'Azeret Mono', monospace;
      font-size: 11px;
      letter-spacing: 0.08em;
      color: rgba(255, 248, 239, 0.62);
      margin-bottom: 14px;
    }
    h1 {
      margin: 0 0 16px;
      font-size: 40px;
      line-height: 1.05;
      font-weight: 900;
      letter-spacing: -0.05em;
    }
    .story p {
      margin: 0;
      color: rgba(255, 248, 239, 0.78);
      line-height: 2;
      font-size: 14px;
    }
    .story-foot {
      margin-top: 28px;
      padding-top: 22px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .chip {
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      font-size: 12px;
      font-weight: 700;
    }
    .login-box {
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    .login-box h2 {
      margin: 0 0 8px;
      font-size: 28px;
      font-weight: 900;
      letter-spacing: -0.04em;
    }
    .login-box .sub {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.9;
      margin-bottom: 28px;
    }
    input {
      width: 100%;
      padding: 15px 16px;
      margin-bottom: 18px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.75);
      border: 1px solid var(--line);
      color: var(--ink);
      font-family: inherit;
      font-size: 15px;
      outline: none;
      transition: 0.2s;
      text-align: left;
      direction: ltr;
    }
    input:focus {
      border-color: rgba(231, 111, 81, 0.45);
      box-shadow: 0 0 0 4px rgba(231, 111, 81, 0.1);
      background: rgba(255, 255, 255, 0.92);
    }
    .btn {
      width: 100%;
      padding: 15px;
      border: none;
      border-radius: 16px;
      background: linear-gradient(135deg, var(--brand), #b84b33);
      color: white;
      font-family: inherit;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      transition: 0.2s;
      box-shadow: 0 18px 26px rgba(184, 75, 51, 0.24);
    }
    .btn:hover { transform: translateY(-1px); }
    .error {
      color: #b63c4c;
      font-size: 13px;
      margin-bottom: 18px;
      background: rgba(209, 73, 91, 0.1);
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid rgba(209, 73, 91, 0.14);
    }
    .tiny {
      margin-top: 16px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.9;
    }
    @media (max-width: 860px) {
      .shell { grid-template-columns: 1fr; }
      .panel { padding: 28px; }
      h1 { font-size: 32px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="panel story">
      <div class="badge">✂️</div>
      <div class="kicker">GHEYCHI PREMIUM / CONTROL ROOM</div>
      <h1>مرکز فرماندهی<br>نسخه‌ی جدید</h1>
      <p>ورود به پنل مدیریتی با ظاهر تازه برای کنترل کاربران، لاگ‌ها، درآمد و تنظیمات سرویس. این لایه برای استفاده‌ی روزانه سریع‌تر و خواناتر بازطراحی شده است.</p>
      <div class="story-foot">
        <span class="chip">Realtime Monitoring</span>
        <span class="chip">Subscriptions</span>
        <span class="chip">Finance</span>
      </div>
    </section>
    <section class="panel login-box">
      <h2>ورود مدیر</h2>
      <div class="sub">برای دسترسی به ابزارهای مدیریت، رمز عبور ادمین را وارد کن.</div>
      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
      <form method="POST" action="/login">
        <input type="password" name="password" placeholder="Admin Password" required autofocus>
        <button type="submit" class="btn">ورود امن</button>
      </form>
      <div class="tiny">نشست مدیریتی بعد از ورود به‌صورت موقت فعال می‌ماند و فرم‌ها با CSRF محافظت می‌شوند.</div>
    </section>
  </div>
</body>
</html>
'''



def _usage_lines_for_user(telegram_user_id: int) -> list[str]:
    snapshot = get_usage_snapshot(telegram_user_id)
    lines: list[str] = []
    for rule in snapshot["rules"]:
        if rule["limit"] is None:
            lines.append(f"{rule['platform']}: نامحدود")
        else:
            lines.append(
                f"{rule['platform']}: {rule['used']}/{rule['limit']} در هر {rule['period_label']}"
            )
    return lines


@app.route("/")
def landing_page():
    return send_file("website/index.html")

    return send_file(file_path)

@app.route("/admin")
@_requires_auth
def admin_index():
    init_logs_db()
    settings = load_settings()
    logs = list_logs(limit=200)

    # Pagination for users
    page = int(request.args.get("page", 1))
    per_page = 20
    total_users = count_bot_users()
    total_pages = (total_users + per_page - 1) // per_page
    offset = (page - 1) * per_page

    users = list_bot_users(limit=per_page, offset=offset)
    for user in users:
        user["usage_lines"] = _usage_lines_for_user(user["telegram_user_id"])

    stats = get_dashboard_stats()
    try:
        analytics_days = int(request.args.get("days", 30))
    except ValueError:
        analytics_days = 30
    analytics_stats = get_analytics_stats(days=analytics_days)
    saved = request.args.get("saved") == "1"
    import os
    env_stripe_secret_set = bool(os.getenv("STRIPE_SECRET_KEY"))
    env_stripe_webhook_set = bool(os.getenv("STRIPE_WEBHOOK_SECRET"))
    
    lang = session.get("admin_lang", "fa")
    from locales import get_text
    def _t(key):
        return get_text(key, lang)

    return render_template_string(
        PAGE_TEMPLATE,
        settings=settings,
        logs=logs,
        stats=stats,
        analytics_stats=analytics_stats,
        analytics_days=analytics_days,
        transactions=list_transactions(limit=100),
        fin_stats=get_financial_stats(),
        users=users,
        plans=list_plans(),
        saved=saved,
        all_platforms=ALLOWED_PLATFORMS,
        format_rule=format_rule,
        flag_map=flag_map,
        plans_json_str=__import__('json').dumps(__import__('plans').get_subscription_plans(), ensure_ascii=False, indent=2),
        env_stripe_secret_set=env_stripe_secret_set,
        env_stripe_webhook_set=env_stripe_webhook_set,
        lang=lang,
        _t=_t,
        page=page,
        total_pages=total_pages,
        total_users=total_users,
    )


@app.post("/plans/update")
@_requires_auth
def update_plans():
    import json
    from plans import save_subscription_plans
    try:
        new_plans = json.loads(request.form.get("plans_json", "{}"))
        save_subscription_plans(new_plans)
        add_log("INFO", "plans_updated", f"اطلاعات پکیج‌های سیستم داینامیک به‌روزرسانی شد.", metadata={"source": "پنل ادمین"})
        return redirect(url_for("admin_index", saved="1"))
    except Exception as e:
        add_log("ERROR", "plans_update_failed", f"فرمت JSON برای برنامه‌ها نامعتبر بود: {e}", metadata={"source": "پنل ادمین"})
        return redirect(url_for("admin_index"))

@app.post("/settings")
@_requires_auth
def update_settings():
    selected_platforms = request.form.getlist("allowed_platforms")
    
    # Load existing to preserve dynamic limits not in this form, then update
    existing_settings = load_settings()
    
    import os
    env_stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    env_stripe_webhook = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    form_stripe_secret = request.form.get("stripe_secret_key", "").strip()
    form_stripe_webhook = request.form.get("stripe_webhook_secret", "").strip()
    
    # Validation logic for environment enforcement
    if (env_stripe_secret and form_stripe_secret and form_stripe_secret != env_stripe_secret) or \
       (env_stripe_webhook and form_stripe_webhook and form_stripe_webhook != env_stripe_webhook):
        add_log("WARNING", "settings_rejected", f"Stripe keys are managed via environment variables and cannot be changed here", metadata={"source": "پنل ادمین"})
        return "سرور در حالت ایزوله (Environment Variables) قرار دارد. شما مجاز به دستکاری کلیدهای مالیِ Stripe از طریق پنل نیستید.", 403
    
    existing_settings.update({
        "max_file_size_mb": request.form.get("max_file_size_mb", 50),
        "downloads_enabled": request.form.get("downloads_enabled") == "1",
        "allowed_platforms": selected_platforms,
        "use_cobalt_api": request.form.get("use_cobalt_api") == "1",
        "cobalt_api_url": request.form.get("cobalt_api_url", ""),
        "cobalt_api_jwt": request.form.get("cobalt_api_jwt", ""),
        "rapidapi_key": request.form.get("rapidapi_key", ""),
        # Only permit storing if they are empty/local
        "stripe_secret_key": form_stripe_secret if not env_stripe_secret else "",
        "stripe_webhook_secret": form_stripe_webhook if not env_stripe_webhook else "",
    })
    
    settings = save_settings(existing_settings)
    add_log(
        "INFO",
        "settings_updated",
        "تنظیمات پنل مدیریت تغییر کرد.",
        metadata=settings,
    )
    return redirect(url_for("admin_index", saved="1"))


@app.post("/subscriptions")
@_requires_auth
def assign_subscription():
    telegram_user_id = int(request.form.get("telegram_user_id", "0"))
    plan_code = request.form.get("plan_code", "free")
    months = int(request.form.get("months", "1"))
    note = request.form.get("assigned_note", "").strip()

    user = assign_user_plan(
        telegram_user_id,
        plan_code,
        months=months,
        note=note,
    )
    add_log(
        "INFO",
        "subscription_assigned",
        "پلن کاربر از پنل مدیریت به‌روزرسانی شد.",
        metadata={
            "telegram_user_id": telegram_user_id,
            "plan_code": plan_code,
            "months": months,
            "plan_expires_at": user["plan_expires_at"],
        },
    )
    return redirect(url_for("admin_index", saved="1"))


@app.get("/api/settings")
@_requires_auth
def settings_api():
    return jsonify(load_settings())


@app.get("/api/logs")
@_requires_auth
def logs_api():
    return jsonify(list_logs(limit=200))


@app.get("/api/users")
@_requires_auth
def users_api():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page

    users = list_bot_users(limit=per_page, offset=offset)
    for user in users:
        user["usage_lines"] = _usage_lines_for_user(user["telegram_user_id"])

    total = count_bot_users()
    return jsonify({
        "users": users,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page
    })



def _send_broadcast_background(text: str, user_ids: list):
    from config import BOT_TOKEN
    import time
    import markdown
    
    # Convert markdown from EasyMDE to HTML for safe telegram sending
    html_text = markdown.markdown(text)
    
    async def _send_all():
        bot = Bot(token=BOT_TOKEN)
        success_count = 0
        error_count = 0
        async with bot:
            for uid in user_ids:
                try:
                    await bot.send_message(chat_id=uid, text=html_text, parse_mode="HTML")
                    success_count += 1
                except Exception as e:
                    error_count += 1
                await asyncio.sleep(0.05)
            
        add_log("INFO", "broadcast_completed", f"ارسال سراسری پایان یافت. موفق: {success_count}، ناموفق: {error_count}", metadata={"source": "پنل ادمین"})
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_send_all())
    loop.close()


@app.get("/backup/download")
@_requires_auth
def download_backup():
    # Directories/Files to include
    include_dirs = ['data']
    include_files = ['bot.py', 'admin_panel.py', 'config.py', 'runtime_store.py', 'plans.py', 'main.py', 'requirements.txt', 'api_client.py', 'downloader.py', '.env']
    
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, 'gheychi_backup.zip')
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add files
            for file_name in include_files:
                if os.path.exists(file_name):
                    zipf.write(file_name)
                    
            # Add data directory recursively
            for dir_name in include_dirs:
                if os.path.exists(dir_name):
                    for root, _, files in os.walk(dir_name):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, os.path.dirname(dir_name))
                            zipf.write(file_path, arcname)
                            
        add_log("INFO", "system_backup", f"یک نسخه پشتیبان کامل از سیستم استخراج شد.", metadata={"source": "پنل ادمین"})
        return send_file(zip_path, as_attachment=True, download_name='gheychi_premium_backup.zip', mimetype='application/zip')
    except Exception as e:
        return f"Backup failed: {str(e)}", 500

@app.post("/broadcast")
@_requires_auth
def send_broadcast():
    text = request.form.get("message_text", "").strip()
    if not text:
        return redirect(url_for("admin_index"))
        
    users = list_bot_users(limit=1000000)
    user_ids = [u["telegram_user_id"] for u in users]
    
    add_log("INFO", "broadcast_started", f"ارسال پیام سراسری برای {len(user_ids)} کاربر آغاز شد.", metadata={"source": "پنل ادمین"})
    
    threading.Thread(target=_send_broadcast_background, args=(text, user_ids), daemon=True).start()
    return redirect(url_for("admin_index", saved="1"))


@app.post("/finance/confirm")
@_requires_auth
def confirm_transaction():
    tx_id = request.form.get("tx_id")
    if not tx_id:
        return redirect(url_for("admin_index"))
        
    tx = get_transaction(tx_id)
    if not tx or tx["status"] != "Pending":
        return redirect(url_for("admin_index"))

    _activate_paid_plan(
        telegram_user_id=tx["telegram_user_id"],
        plan_code=tx["plan_code"],
        note=f"تایید تراکنش معلق: {tx_id}",
        tx_id=tx_id,
    )
    add_log(
        "INFO",
        "transaction_manual_confirm",
        f"تراکنش مالی به صورت دستی تایید شد {tx_id[:12]}.",
        metadata={"source": "پنل ادمین"},
    )

    return redirect(url_for("admin_index", saved="1"))


def _format_payment_success_message(user: dict, plan: dict) -> str:
    """Build a bilingual (fa + en) payment confirmation message with plan
    name, expiry date and per-platform rules. Used by both the Stripe
    webhook and the manual /finance/confirm endpoint."""
    from locales import get_text
    from plans import format_rule

    expiry_iso = user.get("plan_expires_at")
    if expiry_iso:
        # ISO timestamp in UTC; show only the date for clarity
        expiry_short = expiry_iso.split("T", 1)[0]
        expiry_fa = expiry_short
        expiry_en = expiry_short
    else:
        expiry_fa = get_text("payment_success_unlimited_expiry", "fa")
        expiry_en = get_text("payment_success_unlimited_expiry", "en")

    rules_fa = "\n".join(f"• {format_rule(r, 'fa')}" for r in plan.get("rules", [])) or "—"
    rules_en = "\n".join(f"• {format_rule(r, 'en')}" for r in plan.get("rules", [])) or "—"

    plan_name_fa = plan.get("name_fa") or plan.get("name", "")
    plan_name_en = plan.get("name_en") or plan.get("name", "")
    price = plan.get("price_usd", 0)

    fa_part = (
        f"{get_text('payment_success_title', 'fa')}\n\n"
        + get_text(
            "payment_success_body",
            "fa",
            plan_name=plan_name_fa,
            expiry=expiry_fa,
            price=price,
            rules=rules_fa,
        )
    )
    en_part = (
        f"{get_text('payment_success_title', 'en')}\n\n"
        + get_text(
            "payment_success_body",
            "en",
            plan_name=plan_name_en,
            expiry=expiry_en,
            price=price,
            rules=rules_en,
        )
    )
    return f"{fa_part}\n\n━━━━━━━━━━━━━━\n\n{en_part}"


def _send_telegram_message(chat_id: int, text: str) -> bool:
    """Fire-and-forget Telegram send from a sync Flask handler.
    Returns True on success, False otherwise (errors are logged)."""
    try:
        loop = asyncio.new_event_loop()
        try:
            bot = Bot(token=BOT_TOKEN)
            loop.run_until_complete(
                bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            )
        finally:
            loop.close()
        return True
    except Exception as exc:
        add_log(
            "ERROR",
            "telegram_notify_failed",
            f"Failed to send Telegram message to {chat_id}: {str(exc)[:200]}",
            metadata={"telegram_user_id": chat_id},
        )
        return False


def _activate_paid_plan(telegram_user_id: int, plan_code: str, *, note: str, tx_id: str | None = None) -> bool:
    """Activate the plan for the user, mark transaction as completed,
    and send the bilingual confirmation message. Returns True on success."""
    from plans import get_plan
    plan = get_plan(plan_code)
    if not plan:
        add_log("ERROR", "activation_failed", f"Unknown plan_code: {plan_code}",
                metadata={"telegram_user_id": telegram_user_id, "tx_id": tx_id})
        return False

    user = assign_user_plan(
        telegram_user_id,
        plan_code,
        months=1,
        note=note,
    )
    if tx_id:
        update_transaction_status(tx_id, "Completed")

    message = _format_payment_success_message(user, plan)
    _send_telegram_message(telegram_user_id, message)

    add_log(
        "INFO",
        "payment_success",
        f"اشتراک {plan_code} فعال شد و پیام تأیید برای کاربر ارسال شد.",
        metadata={"telegram_user_id": telegram_user_id, "plan_code": plan_code, "tx_id": tx_id},
    )
    return True


@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    
    if not sig_header:
        add_log("ERROR", "webhook_failed", f"Missing Stripe signature", metadata={"source": "پنل ادمین"})
        return "Missing signature", 400

    settings = load_settings()
    active_webhook_secret = settings.get("stripe_webhook_secret") or STRIPE_WEBHOOK_SECRET
    
    if not active_webhook_secret:
        add_log("ERROR", "webhook_failed", f"Stripe webhook secret not configured", metadata={"source": "پنل ادمین"})
        return "Webhook secret missing", 500

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, active_webhook_secret
        )
    except ValueError as e:
        add_log("ERROR", "webhook_failed", f"Invalid payload: {e}", metadata={"source": "پنل ادمین"})
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        add_log("ERROR", "webhook_failed", f"Invalid signature: {e}", metadata={"source": "پنل ادمین"})
        return "Invalid signature", 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        client_reference_id = getattr(session, 'client_reference_id', None)
        
        if not client_reference_id:
            add_log("ERROR", "webhook_failed", f"Missing client_reference_id in session", metadata={"source": "پنل ادمین"})
            return "Missing client_reference_id", 400
            
        try:
            parts = client_reference_id.split("_", 1)
            if len(parts) != 2:
                raise ValueError(f"Malformed client_reference_id: {client_reference_id}")

            user_id_str, plan_code = parts
            user_id = int(user_id_str)

            ok = _activate_paid_plan(
                user_id,
                plan_code,
                note="Stripe Auto-Payment",
                tx_id=session.id,
            )
            if not ok:
                raise ValueError(f"Activation failed for plan {plan_code}")

        except Exception as e:
            error_msg = str(e)[:300]
            add_log("ERROR", "webhook_process_error", error_msg, metadata={"client_reference_id": client_reference_id})
            return f"Processing error: {error_msg}", 500
            
    return jsonify(success=True), 200

# =====================================================================
# USER WEB DASHBOARD ROUTES
# =====================================================================

@app.route("/auth/magic")
def magic_login():
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
    from config import FLASK_SECRET_KEY
    
    token = request.args.get("token")
    if not token:
        return "کد ورود (Token) ارسال نشده است.", 400
    
    serializer = URLSafeTimedSerializer(FLASK_SECRET_KEY)
    try:
        # Token valid for 30 minutes (1800 seconds)
        user_id = serializer.loads(token, salt='magic-link', max_age=1800)
    except SignatureExpired:
        return "لینک ورود شما منقضی شده است. لطفاً از طریق ربات، لینک جدیدی دریافت کنید.", 401
    except BadTimeSignature:
        return "لینک نامعتبر است یا دستکاری شده است.", 401
        
    session["user_id"] = user_id
    return redirect(url_for("user_dashboard"))

@app.route("/dashboard")
def user_dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return "شما وارد نشده‌اید. لطفاً ابتدا از طریق ربات تلگرام روی دکمه ورود کلیک کنید.", 401
        
    from runtime_store import get_bot_user, get_user_download_history
    import os
    
    # 1. Fetch user subscription details
    user = get_bot_user(user_id)
    if not user:
        return "حساب کاربری یافت نشد.", 404
        
    # 2. Fetch history
    history = get_user_download_history(user_id, limit=20)
    
    # 3. Read the template from file
    template_path = os.path.join(os.path.dirname(__file__), "website", "user_dashboard.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()
        
    return render_template_string(template_str, user=user, history=history)

@app.route("/dashboard/upgrade")
def user_dashboard_upgrade():
    # Placeholder for upgrade logic
    return redirect("https://t.me/gheychipremium_bot") # Redirect back to bot for now or to plans logic

@app.route("/auth/logout")
def user_logout():
    session.pop("user_id", None)
    return redirect(url_for("landing_page"))

@app.route("/<path:filename>")
def serve_website_static(filename):
    import os
    if ".." in filename:
        abort(404)
    file_path = os.path.join(os.path.dirname(__file__), "website", filename)
    if not os.path.exists(file_path):
        abort(404)
    return send_file(file_path)

def run_admin_panel() -> None:
    if not ADMIN_PASSWORD:
        import sys
        print("\n" + "="*60)
        print("🚨 CRITICAL SECURITY ALERT: ADMIN_PASSWORD is NOT SET!")
        print("   The admin panel cannot start natively without a password barrier.")
        print("   Set ADMIN_PASSWORD in your Railway variables or .env file.")
        print("="*60 + "\n")
        sys.exit(1)

    import os
    init_logs_db()
    port = os.getenv("PORT", "8080")
    
    try:
        from gunicorn.app.base import BaseApplication
        
        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                config = {key: value for key, value in self.options.items()
                          if key in self.cfg.settings and value is not None}
                for key, value in config.items():
                    self.cfg.set(key.lower(), value)

            def load(self):
                return self.application
                
        options = {
            'bind': f"0.0.0.0:{port}",
            'workers': 2,
            'threads': 2,
            'timeout': 120,
            'accesslog': '-',
            'errorlog': '-'
        }
        print(f"Starting Gunicorn on port {port} with 2 workers...")
        StandaloneApplication(app, options).run()
        
    except ImportError:
        print("WARNING: gunicorn is not installed! Falling back to Flask development server.")
        app.run(host="0.0.0.0", port=int(port), debug=False)

if __name__ == "__main__":
    run_admin_panel()
