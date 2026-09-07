"""
داشبورد مدیریت و سرور گرافیکی وب (Flask Web Server)
ایمن‌سازی صفحات، بررسی نشست‌ها و رابط کاربری پنل ادمین جهت کنترل کامل بات از اینجا فرمان‌دهی می‌شود.
"""
import os
import tempfile
import zipfile
from functools import wraps
import asyncio
import threading
from telegram import Bot
import stripe
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, BOT_TOKEN, BOT_USERNAME, BOT_LINK

from flask import Flask, Response, jsonify, send_file, redirect, render_template_string, request, url_for, session, abort

from config import ADMIN_PASSWORD, ALLOWED_PLATFORMS, SUPPORT_CONTACT
from plans import format_rule, list_plans
from runtime_store import (
    add_log,
    assign_user_plan,
    get_usage_snapshot,
    init_logs_db,
    list_bot_users,
    count_bot_users,
    list_logs,
    count_logs,
    get_dashboard_stats,
    load_settings,
    save_settings,
    list_transactions,
    get_transaction,
    update_transaction_status,
    get_financial_stats,
    get_analytics_stats,
    consume_auth_token,
    rate_limit_hit,
    rate_limit_clear,
)

app = Flask(__name__)
# Security configs
import secrets
from datetime import timedelta
from config import FLASK_SECRET_KEY, BASE_URL

# This used to be os.getenv(..., secrets.token_hex(24)), which differed from the
# constant config.py fell back to. With two gunicorn workers each generating its
# own random key, sessions broke whenever a request hit the other worker, while
# magic links were still validated against the public constant. One key now.
app.secret_key = FLASK_SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=8)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=BASE_URL.startswith("https://"),
)

# Two trust levels share this cookie: the admin and dashboard visitors. Flask
# gives an app exactly one session cookie, so they are kept apart by an explicit
# role claim that every guard checks, and by clearing the session on each login
# so a role can never be carried over from a previous one.
ROLE_ADMIN = "admin"
ROLE_USER = "user"

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
        if not session.get("logged_in") or session.get("role") != ROLE_ADMIN:
            return redirect(url_for("login"))
        return handler(*args, **kwargs)

    return wrapped

@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr or "unknown"

    if request.method == "GET":
        return render_template_string(LOGIN_TEMPLATE)

    # The counter used to be a module-level dict, so each of the two gunicorn
    # workers kept its own and the real ceiling was ten attempts, not five.
    retry_after = rate_limit_hit("admin_login", ip, limit=5, window_seconds=900)
    if retry_after:
        add_log("WARNING", "brute_force_blocked", f"ورود ادمین از {ip} به دلیل تلاش بیش از حد مسدود شد.", metadata={"source": "پنل ادمین"})
        return Response("Too many failed attempts. Try again later.", status=429, headers={"Retry-After": str(retry_after)})

    password = request.form.get("password", "")
    if ADMIN_PASSWORD and secrets.compare_digest(password, ADMIN_PASSWORD):
        session.clear()
        session.permanent = True
        session["logged_in"] = True
        session["role"] = ROLE_ADMIN
        session["csrf_token"] = secrets.token_hex(16)
        rate_limit_clear("admin_login", ip)

        add_log("INFO", "admin_login", f"ورود موفق ادمین از {ip}", metadata={"source": "پنل ادمین"})
        return redirect(url_for("admin_index"))

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

    # Pagination for users
    page = int(request.args.get("page", 1))
    per_page = 20
    total_users = count_bot_users()
    total_pages = (total_users + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # Pagination for logs
    log_page = int(request.args.get("log_page", 1))
    log_per_page = 30
    total_logs = count_logs()
    log_total_pages = (total_logs + log_per_page - 1) // log_per_page
    log_offset = (log_page - 1) * log_per_page
    logs = list_logs(limit=log_per_page, offset=log_offset)

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
    active_tab = request.args.get("tab", "")
    import os
    env_stripe_secret_set = bool(os.getenv("STRIPE_SECRET_KEY"))
    env_stripe_webhook_set = bool(os.getenv("STRIPE_WEBHOOK_SECRET"))
    # The control room template is English; its rule strings follow it rather
    # than the operator's bot language.
    lang = "en"
    from locales import get_text
    def _t(key):
        return get_text(key, lang)

    def format_rule_en(rule):
        return format_rule(rule, "en")

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
        active_tab=active_tab,
        all_platforms=ALLOWED_PLATFORMS,
        format_rule=format_rule_en,
        flag_map=flag_map,
        plans_json_str=__import__('json').dumps(__import__('plans').get_subscription_plans(), ensure_ascii=False, indent=2),
        env_stripe_secret_set=env_stripe_secret_set,
        env_stripe_webhook_set=env_stripe_webhook_set,
        lang=lang,
        _t=_t,
        page=page,
        total_pages=total_pages,
        total_users=total_users,
        log_page=log_page,
        log_total_pages=log_total_pages,
        log_total=total_logs,
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
    
    async def _send_all():
        bot = Bot(token=BOT_TOKEN)
        success_count = 0
        error_count = 0
        async with bot:
            for uid in user_ids:
                try:
                    await bot.send_message(chat_id=uid, text=text)
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    # Log first few errors for debugging
                    if error_count <= 5:
                        add_log("ERROR", "broadcast_error", f"Failed to send to {uid}: {str(e)[:150]}", metadata={"source": "پنل ادمین"})
                await asyncio.sleep(0.05)
            
        add_log("INFO", "broadcast_completed", f"ارسال سراسری پایان یافت. موفق: {success_count}، ناموفق: {error_count}", metadata={"source": "پنل ادمین"})
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_send_all())
    finally:
        loop.close()


@app.get("/backup/download")
@_requires_auth
def download_backup():
    """
    Download a snapshot of the data directory.

    This used to zip a hardcoded 'data' folder plus the source files and .env.
    In production DATA_DIR is /data, so the hardcoded relative path matched
    nothing and the "full backup" contained no database at all — only source
    code that is already in git, and every secret in the repo's .env. It now
    ships the data and nothing else, through the same consistent-snapshot path
    the scheduled backup uses.
    """
    from backup import build_backup_archive

    temp_dir = tempfile.mkdtemp()
    try:
        archive = build_backup_archive(temp_dir)
        add_log("INFO", "system_backup", "یک نسخه پشتیبان از دیتابیس استخراج شد.", metadata={"source": "پنل ادمین"})
        return send_file(
            str(archive),
            as_attachment=True,
            download_name=archive.name,
            mimetype="application/zip",
        )
    except Exception as e:
        add_log("ERROR", "system_backup_failed", f"استخراج نسخه پشتیبان ناموفق بود: {e}", metadata={"source": "پنل ادمین"})
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


@app.route('/webhook/stripe', methods=['GET', 'POST'])
def stripe_webhook():
    # GET: health-check / debug endpoint
    if request.method == 'GET':
        settings = load_settings()
        has_key = bool(settings.get("stripe_secret_key") or STRIPE_SECRET_KEY)
        has_wh = bool(settings.get("stripe_webhook_secret") or STRIPE_WEBHOOK_SECRET)
        return jsonify({
            "webhook": "ready",
            "stripe_secret_key_set": has_key,
            "stripe_webhook_secret_set": has_wh,
            "secret_key_prefix": (settings.get("stripe_secret_key") or STRIPE_SECRET_KEY or "")[:7] + "..." if has_key else "MISSING",
        }), 200

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    add_log("INFO", "webhook_received", f"Stripe webhook hit from {request.remote_addr}", metadata={"source": "پنل ادمین"})

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

    # Set Stripe API key for any downstream Stripe calls
    stripe.api_key = settings.get("stripe_secret_key") or STRIPE_SECRET_KEY

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        # Use dict-style access (works for both dict and StripeObject)
        client_reference_id = session.get('client_reference_id') if isinstance(session, dict) else session.get('client_reference_id', None)
        if not client_reference_id:
            client_reference_id = session['client_reference_id'] if 'client_reference_id' in session else None
        
        if not client_reference_id:
            add_log("ERROR", "webhook_failed", "Missing client_reference_id in session", metadata={"source": "پنل ادمین"})
            return jsonify(success=False, error="Missing client_reference_id"), 200
            
        try:
            parts = client_reference_id.split("_", 1)
            if len(parts) != 2:
                raise ValueError(f"Malformed client_reference_id: {client_reference_id}")

            user_id_str, plan_code = parts
            user_id = int(user_id_str)
            session_id = session.get('id') or session['id']

            add_log("INFO", "webhook_processing", f"Activating plan {plan_code} for user {user_id} (session: {session_id[:12]}...)", metadata={"source": "پنل ادمین"})

            ok = _activate_paid_plan(
                user_id,
                plan_code,
                note="Stripe Auto-Payment",
                tx_id=session_id,
            )
            if not ok:
                raise ValueError(f"Activation failed for plan {plan_code}")

            add_log("INFO", "webhook_success", f"Plan {plan_code} activated for user {user_id}", metadata={"source": "پنل ادمین"})

        except Exception as e:
            error_msg = str(e)[:300]
            add_log("ERROR", "webhook_process_error", error_msg, metadata={"client_reference_id": client_reference_id})
            # Still return 200 so Stripe doesn't keep retrying
            return jsonify(success=False, error=error_msg), 200
            
    return jsonify(success=True), 200

# =====================================================================
# USER WEB DASHBOARD ROUTES
# =====================================================================

def _current_account_id() -> str | None:
    """The signed-in account, or None. Role is checked so an admin session is not one."""
    if session.get("role") != ROLE_USER:
        return None
    return session.get("account_id")


def _start_user_session(account_id: str, telegram_user_id: int | None = None) -> None:
    # Cleared first so a stale admin role can never survive into a user session.
    session.clear()
    session.permanent = True
    session["role"] = ROLE_USER
    session["account_id"] = account_id
    session["csrf_token"] = secrets.token_hex(16)
    if telegram_user_id is not None:
        session["user_id"] = telegram_user_id


def _client_ip() -> str:
    return request.remote_addr or "unknown"


# =====================================================================
# EMAIL SIGN-IN
# =====================================================================

@app.post("/auth/email/request")
def email_request_code():
    """
    Issue a sign-in code.

    The answer is identical whether or not the address has an account. Any
    difference — wording, status, timing — turns this endpoint into a way to
    ask "does this person use Gheychi", which is not ours to disclose.
    """
    from accounts import get_account_by_email, normalise_email
    from auth_codes import PURPOSE_EMAIL_LOGIN, issue_code
    from mailer import send_login_code

    email = normalise_email(request.form.get("email", ""))
    if not email or "@" not in email or len(email) > 254:
        return jsonify(success=False, error="invalid_email"), 400

    ip = _client_ip()
    # Two independent ceilings: one stops a single address being spammed, the
    # other stops one host walking a list of addresses.
    for bucket, key, limit, window in (
        ("email_code_ip", ip, 10, 900),
        ("email_code_addr", email, 5, 900),
    ):
        retry_after = rate_limit_hit(bucket, key, limit, window)
        if retry_after:
            return jsonify(success=False, error="rate_limited", retry_after=retry_after), 429

    existing = get_account_by_email(email)
    lang = "en"
    code = issue_code(PURPOSE_EMAIL_LOGIN, email)
    send_login_code(email, code, lang)
    add_log("INFO", "email_code_issued", f"کد ورود برای {email} صادر شد (اکانت موجود: {bool(existing)})", metadata={"source": "پنل کاربری"})
    return jsonify(success=True)


@app.post("/auth/email/verify")
def email_verify_code():
    """Check the code and sign the account in, creating it on first success."""
    from accounts import create_account, get_account_by_email, normalise_email
    from auth_codes import PURPOSE_EMAIL_LOGIN, CodeError, verify_code

    email = normalise_email(request.form.get("email", ""))
    code = (request.form.get("code") or "").strip()
    if not email or not code:
        return jsonify(success=False, error="missing_fields"), 400

    retry_after = rate_limit_hit("email_verify_ip", _client_ip(), 20, 900)
    if retry_after:
        return jsonify(success=False, error="rate_limited", retry_after=retry_after), 429

    try:
        verify_code(PURPOSE_EMAIL_LOGIN, email, code)
    except CodeError as exc:
        return jsonify(success=False, error=exc.code), 401

    # Created only now, on a proven address — a failed attempt must not leave
    # an account behind, or the table fills with addresses nobody controls.
    account = get_account_by_email(email) or create_account(email)
    _start_user_session(account["account_id"])
    rate_limit_clear("email_code_addr", email)
    add_log("INFO", "email_login", f"ورود با ایمیل: {email}", metadata={"source": "پنل کاربری"})
    return jsonify(success=True, redirect=url_for("account_page"))


# A magic link lives in a Telegram chat forever and travels in a query string,
# so it leaks through Referer headers, browser history and link-preview
# prefetch. Expiry alone does not cover that: anyone who reads the chat inside
# the window can replay it. Hence a short window, one use only, and a redirect
# that gets the token out of the address bar.
MAGIC_LINK_MAX_AGE_SECONDS = 600


@app.route("/auth/magic")
def magic_login():
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

    ip = request.remote_addr or "unknown"
    retry_after = rate_limit_hit("magic_login", ip, limit=10, window_seconds=600)
    if retry_after:
        return Response("Too many attempts. Try again later.", status=429, headers={"Retry-After": str(retry_after)})

    token = request.args.get("token")
    if not token:
        return "کد ورود (Token) ارسال نشده است.", 400

    serializer = URLSafeTimedSerializer(FLASK_SECRET_KEY)
    try:
        payload = serializer.loads(token, salt="magic-link", max_age=MAGIC_LINK_MAX_AGE_SECONDS)
    except SignatureExpired:
        return "لینک ورود شما منقضی شده است. لطفاً از طریق ربات، لینک جدیدی دریافت کنید.", 401
    except BadSignature:
        # BadTimeSignature alone let a plain forged signature through as a 500.
        return "لینک نامعتبر است یا دستکاری شده است.", 401

    # Links minted before the single-use change carried a bare integer. Those
    # cannot be burnt, so they are refused outright rather than trusted.
    if not isinstance(payload, dict) or "uid" not in payload or "jti" not in payload:
        return "این لینک قدیمی است. لطفاً از ربات لینک تازه بگیرید.", 401

    user_id = payload["uid"]
    if not consume_auth_token(payload["jti"], "magic-link", subject=str(user_id)):
        add_log("WARNING", "magic_link_replay", f"تلاش برای استفاده‌ی دوباره از لینک ورود کاربر {user_id} از {ip}", metadata={"source": "پنل ادمین"})
        return "این لینک قبلاً استفاده شده است. لطفاً از ربات لینک تازه بگیرید.", 401

    # The two entry routes have to converge on one account. A user who arrived
    # through the bot first gets an account created here with no email, so that
    # when they later sign up by email and link this same Telegram account they
    # join the account they already have instead of stranding it.
    from accounts import create_account, get_account_by_telegram, link_telegram, LinkError

    account = get_account_by_telegram(user_id)
    if account is None:
        account = create_account()
        try:
            link_telegram(account["account_id"], user_id)
        except LinkError as exc:
            add_log("ERROR", "magic_link_autolink_failed", f"اتصال خودکار کاربر {user_id} ناموفق بود: {exc}", metadata={"source": "پنل کاربری"})
            return "اتصال حساب ممکن نشد. لطفاً با پشتیبانی تماس بگیرید.", 500

    _start_user_session(account["account_id"], telegram_user_id=user_id)

    response = redirect(url_for("user_dashboard"))
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

@app.route("/dashboard")
def user_dashboard():
    """
    Redirect into the account page.

    The bot's buttons, every magic link already sitting in a chat, and the
    marketing pages all point here. Rather than keep two dashboards that drift
    apart, this is now one door into the tabbed account page — where the plan,
    quota and history it used to show live under Overview and Library.
    """
    return redirect(url_for("account_page"))


@app.route("/dashboard/upgrade")
def user_dashboard_upgrade():
    # Placeholder for upgrade logic
    return redirect(BOT_LINK)  # Plans are arranged in the bot until checkout is live

# =====================================================================
# ACCOUNT PROFILE AND TELEGRAM LINKING
# =====================================================================

@app.get("/account")
def account_page():
    """Sign-in screen when signed out, profile when signed in."""
    from accounts import get_account, link_capacity, list_links

    account_id = _current_account_id()
    account = get_account(account_id) if account_id else None

    if account and not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_hex(16)
    elif not account:
        # The sign-in form posts too, so it needs a token before there is a login.
        session.setdefault("csrf_token", secrets.token_hex(16))

    template_path = os.path.join(os.path.dirname(__file__), "website", "account.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()
    return render_template_string(
        template_str,
        account=account,
        links=list_links(account_id) if account else [],
        capacity=link_capacity(account_id) if account else None,
        bot_username=BOT_USERNAME,
        support_contact=SUPPORT_CONTACT,
        csrf_token=session.get("csrf_token"),
    )


@app.post("/account/link/start")
def account_link_start():
    """
    Hand back a deep link and a six-digit code for attaching a Telegram account.

    Both point at the same pending link. The deep link is one tap on a phone;
    the code covers the case where the site is on a desktop and Telegram is
    only on the phone, so nothing can be tapped across the gap.
    """
    from auth_codes import PURPOSE_LINK_CODE, PURPOSE_LINK_DEEP, generate_token, issue_code

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401

    retry_after = rate_limit_hit("link_start", account_id, 10, 900)
    if retry_after:
        return jsonify(success=False, error="rate_limited", retry_after=retry_after), 429

    token = generate_token()
    issue_code(PURPOSE_LINK_DEEP, account_id, code=token)
    code = issue_code(PURPOSE_LINK_CODE, account_id)
    return jsonify(
        success=True,
        deep_link=f"https://t.me/{BOT_USERNAME}?start=link_{token}",
        code=code,
        expires_in=300,
    )


@app.get("/account/links")
def account_links():
    """Polled by the profile so a link confirmed in Telegram appears without a reload."""
    from accounts import link_capacity, list_links

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401
    return jsonify(success=True, links=list_links(account_id), capacity=link_capacity(account_id))


@app.post("/account/unlink")
def account_unlink():
    from accounts import unlink_telegram, UNLINK_COOLDOWN_DAYS

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401

    try:
        telegram_user_id = int(request.form.get("telegram_user_id", ""))
    except (TypeError, ValueError):
        return jsonify(success=False, error="invalid_id"), 400

    if not unlink_telegram(account_id, telegram_user_id):
        return jsonify(success=False, error="not_linked"), 404

    add_log("INFO", "telegram_unlinked", f"اکانت تلگرام {telegram_user_id} از حساب جدا شد.", metadata={"source": "پنل کاربری"})
    return jsonify(success=True, cooldown_days=UNLINK_COOLDOWN_DAYS)


# =====================================================================
# DASHBOARD DATA: HISTORY, STATS, BILLING
# =====================================================================

def _primary_telegram_id(account_id: str) -> int | None:
    """
    Which Telegram account a purchase is credited to.

    The plan still lives on bot_users, so a web purchase has to name one. The
    session's own account wins when there is one, else the oldest link — the
    one most likely to be the person's main account.
    """
    from accounts import list_links

    session_tg = session.get("user_id")
    links = list_links(account_id)
    ids = [l["telegram_user_id"] for l in links]
    if session_tg in ids:
        return session_tg
    return ids[0] if ids else None


@app.get("/account/history")
def account_history_data():
    import stats

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401
    return jsonify(success=True, history=stats.account_history(account_id))


@app.get("/account/stats")
def account_stats_data():
    import stats

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401
    return jsonify(success=True, stats=stats.account_stats(account_id))


@app.get("/account/billing")
def account_billing_data():
    import billing
    from accounts import account_plan_code

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401

    plan_code = account_plan_code(account_id)
    return jsonify(
        success=True,
        current_plan=plan_code,
        invoices=billing.account_invoices(account_id),
        options=billing.upgrade_options(plan_code),
        stripe_ready=billing.is_configured(),
        can_purchase=_primary_telegram_id(account_id) is not None,
    )


@app.post("/account/billing/checkout")
def account_billing_checkout():
    """Start a Stripe Checkout for an upgrade and hand back the URL."""
    import billing

    account_id = _current_account_id()
    if not account_id:
        return jsonify(success=False, error="not_signed_in"), 401

    retry_after = rate_limit_hit("checkout", account_id, 10, 900)
    if retry_after:
        return jsonify(success=False, error="rate_limited", retry_after=retry_after), 429

    plan_code = (request.form.get("plan_code") or "").strip()
    telegram_user_id = _primary_telegram_id(account_id)

    try:
        url = billing.create_checkout_session(
            account_id,
            plan_code,
            telegram_user_id,
            success_url=f"{BASE_URL}/account?paid=1",
            cancel_url=f"{BASE_URL}/account?paid=0",
        )
    except billing.BillingError as exc:
        return jsonify(success=False, error=exc.code), 400
    except Exception as exc:
        add_log("ERROR", "checkout_failed", f"ساخت جلسه پرداخت ناموفق بود: {exc}", metadata={"source": "پنل کاربری"})
        return jsonify(success=False, error="checkout_failed"), 500

    add_log("INFO", "checkout_started", f"پرداخت {plan_code} برای کاربر {telegram_user_id} از پنل آغاز شد.", metadata={"source": "پنل کاربری"})
    return jsonify(success=True, url=url)


@app.route("/auth/logout")
def user_logout():
    session.clear()
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
    from plans import ensure_plan_defaults
    ensure_plan_defaults()
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
