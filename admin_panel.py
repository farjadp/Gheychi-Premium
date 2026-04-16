from functools import wraps
import asyncio
import threading
from telegram import Bot
import stripe
from config import STRIPE_WEBHOOK_SECRET, BOT_TOKEN

from flask import Flask, Response, jsonify, redirect, render_template_string, request, url_for

from config import ADMIN_PASSWORD, ALLOWED_PLATFORMS
from plans import format_rule, list_plans
from runtime_store import (
    add_log,
    assign_user_plan,
    get_usage_snapshot,
    init_logs_db,
    list_bot_users,
    list_logs,
    get_dashboard_stats,
    load_settings,
    save_settings,
)

app = Flask(__name__)

PAGE_TEMPLATE = """
<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gheychi Premium — پنل مدیریت</title>
  <style>
    :root {
      --bg:       #0d0f14;
      --surface:  #13161d;
      --card:     #1a1e28;
      --border:   #252a38;
      --ink:      #e8eaf0;
      --muted:    #7a8099;
      --accent:   #6c8aff;
      --accent2:  #a78bfa;
      --green:    #34d399;
      --red:      #f87171;
      --yellow:   #fbbf24;
      --radius:   16px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: "Inter", "SF Pro Display", system-ui, sans-serif;
      background: var(--bg);
      color: var(--ink);
      min-height: 100vh;
    }

    /* ── Sidebar ── */
    .sidebar {
      position: fixed; top: 0; right: 0;
      width: 240px; height: 100vh;
      background: var(--surface);
      border-left: 1px solid var(--border);
      display: flex; flex-direction: column;
      padding: 24px 16px;
      z-index: 100;
    }
    .logo {
      display: flex; align-items: center; gap: 10px;
      padding: 0 8px 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
    }
    .logo-icon {
      width: 36px; height: 36px; border-radius: 10px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      display: flex; align-items: center; justify-content: center;
      font-size: 18px;
    }
    .logo-text { font-weight: 700; font-size: 15px; line-height: 1.2; }
    .logo-text span { display: block; font-size: 11px; color: var(--muted); font-weight: 400; }
    .nav-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 12px; border-radius: 10px;
      color: var(--muted); font-size: 14px; font-weight: 500;
      cursor: pointer; transition: all .15s; margin-bottom: 2px;
      text-decoration: none; border: none; background: none; width: 100%; text-align: right;
    }
    .nav-item:hover, .nav-item.active {
      background: rgba(108,138,255,.1); color: var(--accent);
    }
    .nav-item .icon { font-size: 16px; width: 20px; text-align: center; }

    /* ── Main ── */
    .main { margin-right: 240px; padding: 28px 32px; max-width: 1200px; }

    /* ── Topbar ── */
    .topbar {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 28px;
    }
    .page-title { font-size: 22px; font-weight: 700; }
    .flash {
      display: flex; align-items: center; gap: 8px;
      background: rgba(52,211,153,.1); color: var(--green);
      border: 1px solid rgba(52,211,153,.2);
      border-radius: 10px; padding: 10px 16px; font-size: 14px;
    }

    /* ── Stats ── */
    .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 28px; }
    .stat-card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px;
    }
    .stat-card .label { font-size: 12px; color: var(--muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em; }
    .stat-card .value { font-size: 32px; font-weight: 700; }
    .stat-card .sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
    .stat-card.green .value { color: var(--green); }
    .stat-card.red .value { color: var(--red); }
    .stat-card.blue .value { color: var(--accent); }
    .stat-card.purple .value { color: var(--accent2); }

    /* ── Tabs ── */
    .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--border); padding-bottom: 0; }
    .tab-btn {
      padding: 10px 18px; border-radius: 8px 8px 0 0; font-size: 14px;
      font-weight: 500; cursor: pointer; border: none; background: none;
      color: var(--muted); transition: all .15s; border-bottom: 2px solid transparent;
      margin-bottom: -1px;
    }
    .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
    .tab-btn:hover:not(.active) { color: var(--ink); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* ── Grid ── */
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; }

    /* ── Card ── */
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 24px;
    }
    .card-title {
      font-size: 15px; font-weight: 600; margin-bottom: 20px;
      display: flex; align-items: center; gap: 8px;
    }
    .card-title .icon { opacity: .7; }

    /* ── Form ── */
    .field { margin-bottom: 16px; }
    .field label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; font-weight: 500; }
    .field input, .field select, .field textarea {
      width: 100%; background: var(--surface); border: 1px solid var(--border);
      color: var(--ink); border-radius: 10px; padding: 10px 14px;
      font: inherit; font-size: 14px; transition: border-color .15s;
    }
    .field input:focus, .field select:focus, .field textarea:focus {
      outline: none; border-color: var(--accent);
    }
    .field textarea { min-height: 80px; resize: vertical; }
    .toggle-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 0; border-bottom: 1px solid var(--border);
    }
    .toggle-row:last-child { border-bottom: none; }
    .toggle-label { font-size: 14px; }
    .toggle-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
    /* iOS-style toggle */
    .toggle { position: relative; display: inline-block; width: 42px; height: 24px; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute; inset: 0; background: var(--border);
      border-radius: 24px; cursor: pointer; transition: .2s;
    }
    .slider:before {
      content: ""; position: absolute;
      width: 18px; height: 18px; left: 3px; bottom: 3px;
      background: white; border-radius: 50%; transition: .2s;
    }
    .toggle input:checked + .slider { background: var(--accent); }
    .toggle input:checked + .slider:before { transform: translateX(18px); }
    .checks-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 12px 0 20px; }
    .check-item {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 10px; border-radius: 8px;
      border: 1px solid var(--border); font-size: 13px; cursor: pointer;
      transition: border-color .15s;
    }
    .check-item:has(input:checked) { border-color: var(--accent); background: rgba(108,138,255,.06); }
    .check-item input { accent-color: var(--accent); width: 15px; height: 15px; }
    .btn {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 10px 20px; border-radius: 10px; font: inherit;
      font-size: 14px; font-weight: 600; cursor: pointer; border: none;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: white; transition: opacity .15s;
    }
    .btn:hover { opacity: .88; }
    .btn-sm { padding: 7px 14px; font-size: 13px; }

    /* ── Table ── */
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    thead th {
      text-align: right; padding: 10px 14px;
      color: var(--muted); font-size: 11px; font-weight: 600;
      text-transform: uppercase; letter-spacing: .06em;
      border-bottom: 1px solid var(--border);
    }
    tbody td {
      padding: 12px 14px; border-bottom: 1px solid rgba(37,42,56,.6);
      vertical-align: top; line-height: 1.5;
    }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: rgba(255,255,255,.02); }
    .cell-main { font-weight: 500; }
    .cell-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }

    /* ── Badges ── */
    .badge {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 3px 10px; border-radius: 999px;
      font-size: 11px; font-weight: 600;
    }
    .badge.INFO, .badge.ok { background: rgba(52,211,153,.12); color: var(--green); }
    .badge.ERROR, .badge.err { background: rgba(248,113,113,.12); color: var(--red); }
    .badge.WARN { background: rgba(251,191,36,.12); color: var(--yellow); }
    .badge.plan-free { background: rgba(122,128,153,.15); color: var(--muted); }
    .badge.plan-starter { background: rgba(52,211,153,.12); color: var(--green); }
    .badge.plan-standard { background: rgba(108,138,255,.15); color: var(--accent); }
    .badge.plan-pro { background: rgba(167,139,250,.15); color: var(--accent2); }

    /* ── Plan cards ── */
    .plan-card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px;
    }
    .plan-name { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
    .plan-price { font-size: 24px; font-weight: 800; color: var(--accent); margin-bottom: 4px; }
    .plan-price span { font-size: 13px; font-weight: 400; color: var(--muted); }
    .plan-desc { font-size: 12px; color: var(--muted); margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
    .plan-rule { font-size: 12px; color: var(--muted); padding: 5px 0; display: flex; align-items: center; gap: 6px; }
    .plan-rule::before { content: "•"; color: var(--accent); font-size: 16px; line-height: 1; }

    /* ── URL cell ── */
    .url-cell { max-width: 220px; word-break: break-all; color: var(--muted); font-size: 12px; }

    /* ── Avatar ── */
    .avatar {
      width: 32px; height: 32px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 13px; font-weight: 700; color: white; flex-shrink: 0;
    }
    .user-cell { display: flex; align-items: center; gap: 10px; }

    /* ── Responsive ── */
    @media (max-width: 1024px) {
      .sidebar { display: none; }
      .main { margin-right: 0; padding: 20px 16px; }
      .stats { grid-template-columns: repeat(2,1fr); }
      .grid-2, .grid-3 { grid-template-columns: 1fr; }
    }
    @media (max-width: 600px) {
      .stats { grid-template-columns: 1fr 1fr; }
      .checks-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-icon">✂️</div>
      <div class="logo-text">Gheychi Premium<span>پنل مدیریت</span></div>
    </div>
    <button class="nav-item active" onclick="showTab('dashboard')">
      <span class="icon">📊</span> داشبورد
    </button>
    <button class="nav-item" onclick="showTab('settings')">
      <span class="icon">⚙️</span> تنظیمات
    </button>
    <button class="nav-item" onclick="showTab('subscriptions')">
      <span class="icon">💳</span> اشتراک‌ها
    </button>
    <button class="nav-item" onclick="showTab('plans')">
      <span class="icon">📦</span> پلن‌ها
    </button>
    <button class="nav-item" onclick="showTab('broadcast')">
      <span class="icon">📢</span> پیام سراسری
    </button>
    <button class="nav-item" onclick="showTab('logs')">
      <span class="icon">📋</span> لاگ‌ها
    </button>
  </aside>

  <!-- Main -->
  <main class="main">

    <div class="topbar">
      <div class="page-title" id="page-title">داشبورد</div>
      {% if saved %}
        <div class="flash">✅ تغییرات با موفقیت ذخیره شد</div>
      {% endif %}
    </div>

    <!-- Stats -->
    <div class="stats">
      <div class="stat-card blue">
        <div class="label">کل رویدادها</div>
        <div class="value">{{ stats.total_logs }}</div>
        <div class="sub">در پایگاه داده</div>
      </div>
      <div class="stat-card red">
        <div class="label">خطاها</div>
        <div class="value">{{ stats.errors }}</div>
        <div class="sub">از کل رویدادها</div>
      </div>
      <div class="stat-card green">
        <div class="label">کاربران</div>
        <div class="value">{{ stats.users }}</div>
        <div class="sub">ثبت‌شده</div>
      </div>
      <div class="stat-card purple">
        <div class="label">اشتراک فعال</div>
        <div class="value">{{ stats.paid_users }}</div>
        <div class="sub">پلن پولی</div>
      </div>
    </div>

    <!-- ── TAB: Dashboard ── -->
    <div class="tab-panel active" id="tab-dashboard">
      <div class="grid-2">
        <!-- Recent logs preview -->
        <div class="card">
          <div class="card-title"><span class="icon">🕐</span> آخرین رویدادها</div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>زمان</th><th>سطح</th><th>رویداد</th><th>پلتفرم</th></tr></thead>
              <tbody>
                {% for log in logs[:10] %}
                <tr>
                  <td><div class="cell-sub">{{ log.created_at[11:19] }}</div></td>
                  <td><span class="badge {{ log.level }}">{{ log.level }}</span></td>
                  <td><div class="cell-main">{{ log.event_type }}</div></td>
                  <td><div class="cell-sub">{{ log.platform or "—" }}</div></td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
        <!-- Users preview -->
        <div class="card">
          <div class="card-title"><span class="icon">👥</span> کاربران اخیر</div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>کاربر</th><th>پلن</th><th>وضعیت</th></tr></thead>
              <tbody>
                {% for user in users[:8] %}
                <tr>
                  <td>
                    <div class="user-cell">
                      <div class="avatar">{{ (user.first_name or 'U')[0] }}</div>
                      <div>
                        <div class="cell-main">{{ user.first_name or '—' }} <span style="font-size:11px">{{ flag_map(user.language_code) if user.language_code else '' }}</span></div>
                        <div class="cell-sub">@{{ user.username or '—' }}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span class="badge plan-{{ user.effective_plan_code }}">
                      {{ user.effective_plan.name }}
                    </span>
                  </td>
                  <td>
                    {% if user.is_subscription_active %}
                      <span class="badge ok">فعال</span>
                    {% else %}
                      <span class="badge err">منقضی</span>
                    {% endif %}
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ── TAB: Settings ── -->
    <div class="tab-panel" id="tab-settings">
      <div class="grid-2">
        <div class="card">
          <div class="card-title"><span class="icon">⚙️</span> تنظیمات سرویس</div>
          <form method="post" action="{{ url_for('update_settings') }}">
            <div class="field">
              <label>حداکثر حجم فایل (مگابایت)</label>
              <input type="number" name="max_file_size_mb" min="1" max="2000" value="{{ settings.max_file_size_mb }}">
            </div>
            <div class="toggle-row">
              <div>
                <div class="toggle-label">فعال بودن دانلود</div>
                <div class="toggle-sub">غیرفعال کردن برای تعمیر و نگهداری</div>
              </div>
              <label class="toggle">
                <input type="checkbox" name="downloads_enabled" value="1" {% if settings.downloads_enabled %}checked{% endif %}>
                <span class="slider"></span>
              </label>
            </div>
            <div style="margin-top:20px; margin-bottom:10px; font-size:13px; color:var(--muted);">پلتفرم‌های مجاز</div>
            <div class="checks-grid">
              {% for platform in all_platforms %}
                <label class="check-item">
                  <input type="checkbox" name="allowed_platforms" value="{{ platform }}" {% if platform in settings.allowed_platforms %}checked{% endif %}>
                  {{ platform }}
                </label>
              {% endfor %}
            </div>
            
            <div style="margin-top:24px; padding-top:16px; border-top:1px solid var(--border);">
              <div class="card-title" style="margin-bottom:12px; font-size:14px;"><span class="icon">🔑</span> کلیدها و توکن‌های اتصال (Advanced API)</div>
              
              <div class="toggle-row" style="padding: 6px 0;">
                <div>
                  <div class="toggle-label">استفاده از API کبالت</div>
                  <div class="toggle-sub">برای دانلود ایمن از Twitter و Instagram</div>
                </div>
                <label class="toggle">
                  <input type="checkbox" name="use_cobalt_api" value="1" {% if settings.use_cobalt_api %}checked{% endif %}>
                  <span class="slider"></span>
                </label>
              </div>
              <div class="field" style="margin-top:10px;">
                <label>Cobalt API URL</label>
                <input type="text" name="cobalt_api_url" value="{{ settings.cobalt_api_url or '' }}" placeholder="https://api.cobalt.tools/">
              </div>
              <div class="field">
                <label>RapidAPI Key (پشتیبان)</label>
                <input type="password" name="rapidapi_key" value="{{ settings.rapidapi_key or '' }}" placeholder="اختیاری">
              </div>
              
              <div style="margin-top:20px; font-size:13px; font-weight:600; color:var(--accent);">Stripe Payment Gateway</div>
              <div class="field" style="margin-top:10px;">
                <label>Stripe Secret Key (sk_live_...)</label>
                <input type="password" name="stripe_secret_key" value="{{ settings.stripe_secret_key or '' }}" placeholder="sk_...">
              </div>
              <div class="field">
                <label>Stripe Webhook Secret (whsec_...)</label>
                <input type="password" name="stripe_webhook_secret" value="{{ settings.stripe_webhook_secret or '' }}" placeholder="whsec_...">
              </div>
            </div>
            
            <button class="btn" style="width:100%; justify-content:center; margin-top:10px;" type="submit">💾 ذخیره کل تنظیمات</button>
          </form>
          <p style="font-size:12px;color:var(--muted);margin-top:14px;">آخرین به‌روزرسانی: {{ settings.updated_at }}</p>
        </div>
      </div>
    </div>

    <!-- ── TAB: Subscriptions ── -->
    <div class="tab-panel" id="tab-subscriptions">
      <div class="grid-2" style="align-items:start">
        <div class="card">
          <div class="card-title"><span class="icon">💳</span> اختصاص اشتراک</div>
          <form method="post" action="{{ url_for('assign_subscription') }}">
            <div class="field">
              <label>Telegram User ID</label>
              <input type="number" name="telegram_user_id" placeholder="مثلاً: 123456789" required>
            </div>
            <div class="field">
              <label>پلن</label>
              <select name="plan_code">
                {% for plan in plans %}
                  <option value="{{ plan.code }}">{{ plan.name }} — ${{ plan.price_usd }}/ماه</option>
                {% endfor %}
              </select>
            </div>
            <div class="field">
              <label>تعداد ماه</label>
              <input type="number" name="months" min="1" value="1">
            </div>
            <div class="field">
              <label>یادداشت (اختیاری)</label>
              <textarea name="assigned_note" placeholder="مثلاً: پرداخت از طریق واریز مستقیم"></textarea>
            </div>
            <button class="btn" type="submit">✅ ثبت یا تمدید اشتراک</button>
          </form>
        </div>

        <div class="card">
          <div class="card-title"><span class="icon">👥</span> لیست کاربران</div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>کاربر</th>
                  <th>پلن فعال</th>
                  <th>انقضا</th>
                  <th>مصرف</th>
                </tr>
              </thead>
              <tbody>
                {% for user in users %}
                <tr>
                  <td>
                    <div class="user-cell">
                      <div class="avatar">{{ (user.first_name or 'U')[0] }}</div>
                      <div>
                        <div class="cell-main">{{ user.first_name or '—' }} <span style="font-size:11px">{{ flag_map(user.language_code) if user.language_code else '' }}</span></div>
                        <div class="cell-sub">@{{ user.username or '—' }} · {{ user.telegram_user_id }}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span class="badge plan-{{ user.effective_plan_code }}">{{ user.effective_plan.name }}</span>
                    {% if not user.is_subscription_active and user.plan_code != 'free' %}
                      <div class="cell-sub" style="color:var(--red)">منقضی</div>
                    {% endif %}
                    {% if user.assigned_note %}
                      <div class="cell-sub">{{ user.assigned_note }}</div>
                    {% endif %}
                  </td>
                  <td><div class="cell-sub">{{ user.plan_expires_at[:10] if user.plan_expires_at else '∞' }}</div></td>
                  <td>
                    {% for line in user.usage_lines %}
                      <div class="cell-sub">{{ line }}</div>
                    {% endfor %}
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ── TAB: Broadcast ── -->
    <div class="tab-panel" id="tab-broadcast">
      <div class="card">
        <div class="card-title"><span class="icon">📢</span> ارسال پیام سراسری (Broadcast)</div>
        <p style="font-size:13px;color:var(--muted);margin-bottom:16px;">
          توجه: پیام شما با سرعت کنترل‌شده‌ای (جهت جلوگیری از بن‌شدن توسط تلگرام) به تمام کاربرانی که دیتابیس هستند ارسال می‌شود. وضعیتِ پایان در بخش لاگ‌ها مشخص خواهد شد.
        </p>
        <form method="post" action="{{ url_for('send_broadcast') }}">
          <div class="field">
            <label>متن پیام (پشتیبانی از Markdown تلگرام)</label>
            <textarea name="message_text" placeholder="مثلاً: *کاربران گرامی*
تخفیف ویژه آغاز شد!" style="min-height: 150px" required></textarea>
          </div>
          <button class="btn" type="submit">🚀 شروع ارسال سراسری به {{ stats.users }} کاربر</button>
        </form>
      </div>
    </div>

    <!-- ── TAB: Plans ── -->
    <div class="tab-panel" id="tab-plans">
      <div class="grid-2">
        {% for plan in plans %}
        <div class="plan-card">
          <div class="plan-name">{{ plan.name }}</div>
          <div class="plan-price">
            {% if plan.price_usd == 0 %}رایگان{% else %}${{ plan.price_usd }}<span>/ماه</span>{% endif %}
          </div>
          <div class="plan-desc">{{ plan.description }}</div>
          {% for rule in plan.rules %}
            <div class="plan-rule">{{ format_rule(rule) }}</div>
          {% endfor %}
        </div>
        {% endfor %}
      </div>
    </div>

    <!-- ── TAB: Logs ── -->
    <div class="tab-panel" id="tab-logs">
      <div class="card">
        <div class="card-title"><span class="icon">📋</span> لاگ‌های سیستم</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>زمان</th>
                <th>سطح</th>
                <th>رویداد</th>
                <th>شرح</th>
                <th>پلتفرم</th>
                <th>لینک</th>
                <th>مسیر (Source)</th>
              </tr>
            </thead>
            <tbody>
              {% for log in logs %}
              <tr>
                <td><div class="cell-sub" style="white-space:nowrap">{{ log.created_at[5:19].replace('T',' ') }}</div></td>
                <td><span class="badge {{ log.level }}">{{ log.level }}</span></td>
                <td><div class="cell-main">{{ log.event_type }}</div></td>
                <td style="max-width:320px"><div class="cell-sub">{{ log.message[:120] }}</div></td>
                <td><div class="cell-sub">{{ log.platform or "—" }}</div></td>
                <td><div class="url-cell">{{ log.url[:60] ~ '…' if log.url and log.url|length > 60 else (log.url or "—") }}</div></td>
                <td>
                  {% if log.metadata and log.metadata.get('source') %}
                    <span class="badge INFO">{{ log.metadata.get('source') }}</span>
                  {% else %}
                    <span style="color:var(--muted)">—</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </main>

  <script>
    const titles = {
      dashboard: 'داشبورد', settings: 'تنظیمات', broadcast: 'پیام سراسری',
      subscriptions: 'اشتراک‌ها', plans: 'پلن‌ها', logs: 'لاگ‌ها'
    };
    function showTab(name) {
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-' + name).classList.add('active');
      document.querySelectorAll('.nav-item').forEach(b => {
        if (b.getAttribute('onclick') === "showTab('" + name + "')") b.classList.add('active');
      });
      document.getElementById('page-title').textContent = titles[name];
    }
    {% if saved %}
      setTimeout(() => document.querySelector('.flash') && (document.querySelector('.flash').style.opacity = '0'), 3000);
    {% endif %}

    // --- Table Pagination & Sorting ---
    function makeTableInteractive(tableId, rowsPerPage) {
      const table = document.getElementById(tableId);
      if (!table) return;
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      let currentPage = 1;
      let currentSortCol = -1;
      let sortDir = 1;

      // Add wrapper for pagination controls
      const controls = document.createElement('div');
      controls.className = 'pagination-controls';
      controls.style.display = 'flex';
      controls.style.justifyContent = 'space-between';
      controls.style.alignItems = 'center';
      controls.style.marginTop = '15px';
      controls.style.fontSize = '13px';
      
      const infoSpan = document.createElement('span');
      infoSpan.style.color = 'var(--muted)';
      const btnGroup = document.createElement('div');
      btnGroup.style.display = 'flex';
      btnGroup.style.gap = '5px';
      
      const prevBtn = document.createElement('button');
      prevBtn.textContent = 'قبلی';
      prevBtn.className = 'btn btn-sm';
      const nextBtn = document.createElement('button');
      nextBtn.textContent = 'بعدی';
      nextBtn.className = 'btn btn-sm';
      
      btnGroup.appendChild(prevBtn);
      btnGroup.appendChild(nextBtn);
      controls.appendChild(infoSpan);
      controls.appendChild(btnGroup);
      table.parentElement.appendChild(controls);

      function renderTable() {
        const totalPages = Math.ceil(rows.length / rowsPerPage) || 1;
        if (currentPage > totalPages) currentPage = totalPages;
        if (currentPage < 1) currentPage = 1;
        
        infoSpan.textContent = `صفحه ${currentPage} از ${totalPages} (تعداد کل: ${rows.length})`;
        
        tbody.innerHTML = '';
        const start = (currentPage - 1) * rowsPerPage;
        const end = start + rowsPerPage;
        rows.slice(start, end).forEach(r => tbody.appendChild(r));
        
        prevBtn.disabled = currentPage === 1;
        nextBtn.disabled = currentPage === totalPages;
        prevBtn.style.opacity = prevBtn.disabled ? '0.5' : '1';
        nextBtn.style.opacity = nextBtn.disabled ? '0.5' : '1';
      }

      function sortTable(colIndex) {
        if (currentSortCol === colIndex) {
          sortDir *= -1;
        } else {
          currentSortCol = colIndex;
          sortDir = 1;
        }
        rows.sort((a, b) => {
          const aText = a.children[colIndex].textContent.trim();
          const bText = b.children[colIndex].textContent.trim();
          return aText.localeCompare(bText, 'fa') * sortDir;
        });
        renderTable();
      }

      // Add sort listeners to headers
      const ths = table.querySelectorAll('thead th');
      ths.forEach((th, idx) => {
        th.style.cursor = 'pointer';
        th.title = 'برای مرتب‌سازی کلیک کنید';
        th.addEventListener('click', () => {
           sortTable(idx);
           ths.forEach(h => h.textContent = h.textContent.replace(' ↕', '').replace(' ↓', '').replace(' ↑', ''));
           th.textContent += sortDir === 1 ? ' ↓' : ' ↑';
        });
      });

      prevBtn.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderTable(); } });
      nextBtn.addEventListener('click', () => { if (currentPage < Math.ceil(rows.length / rowsPerPage)) { currentPage++; renderTable(); } });

      // Init
      ths.forEach(h => h.textContent += ' ↕');
      renderTable();
    }

    // Initialize tables once dom is loaded
    document.addEventListener("DOMContentLoaded", () => {
      // Add ids to tables first
      const usersTable = document.querySelector('#tab-subscriptions table');
      if (usersTable) usersTable.id = 'usersTable';
      const logsTable = document.querySelector('#tab-logs table');
      if (logsTable) logsTable.id = 'logsTable';
      
      makeTableInteractive('usersTable', 10);
      makeTableInteractive('logsTable', 15);
    });

  </script>
</body>
</html>
"""


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
        if not ADMIN_PASSWORD:
            return handler(*args, **kwargs)

        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Admin Panel"'},
            )
        return handler(*args, **kwargs)

    return wrapped


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
@_requires_auth
def index():
    init_logs_db()
    settings = load_settings()
    logs = list_logs(limit=200)
    users = list_bot_users(limit=100)
    for user in users:
        user["usage_lines"] = _usage_lines_for_user(user["telegram_user_id"])

    stats = get_dashboard_stats()
    saved = request.args.get("saved") == "1"
    return render_template_string(
        PAGE_TEMPLATE,
        settings=settings,
        logs=logs,
        stats=stats,
        users=users,
        plans=list_plans(),
        saved=saved,
        all_platforms=ALLOWED_PLATFORMS,
        format_rule=format_rule,
        flag_map=flag_map,
        plans_json_str=__import__('json').dumps(__import__('plans').get_subscription_plans(), ensure_ascii=False, indent=2)
    )


@app.post("/plans/update")
@_requires_auth
def update_plans():
    import json
    from plans import save_subscription_plans
    try:
        new_plans = json.loads(request.form.get("plans_json", "{}"))
        save_subscription_plans(new_plans)
        add_log("INFO", "plans_updated", "اطلاعات پکیج‌های سیستم داینامیک به‌روزرسانی شد.")
        return redirect(url_for("index", saved="1"))
    except Exception as e:
        add_log("ERROR", "plans_update_failed", f"فرمت JSON برای برنامه‌ها نامعتبر بود: {e}")
        return redirect(url_for("index"))

@app.post("/settings")
@_requires_auth
def update_settings():
    selected_platforms = request.form.getlist("allowed_platforms")
    
    # Load existing to preserve dynamic limits not in this form, then update
    existing_settings = load_settings()
    existing_settings.update({
        "max_file_size_mb": request.form.get("max_file_size_mb", 50),
        "downloads_enabled": request.form.get("downloads_enabled") == "1",
        "allowed_platforms": selected_platforms,
        "use_cobalt_api": request.form.get("use_cobalt_api") == "1",
        "cobalt_api_url": request.form.get("cobalt_api_url", ""),
        "rapidapi_key": request.form.get("rapidapi_key", ""),
        "stripe_secret_key": request.form.get("stripe_secret_key", ""),
        "stripe_webhook_secret": request.form.get("stripe_webhook_secret", ""),
    })
    
    settings = save_settings(existing_settings)
    add_log(
        "INFO",
        "settings_updated",
        "تنظیمات پنل مدیریت تغییر کرد.",
        metadata=settings,
    )
    return redirect(url_for("index", saved="1"))


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
    return redirect(url_for("index", saved="1"))


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
    users = list_bot_users(limit=200)
    for user in users:
        user["usage_lines"] = _usage_lines_for_user(user["telegram_user_id"])
    return jsonify(users)



def _send_broadcast_background(text: str, user_ids: list):
    from config import BOT_TOKEN
    import time
    
    async def _send_all():
        bot = Bot(token=BOT_TOKEN)
        success_count = 0
        error_count = 0
        for uid in user_ids:
            try:
                await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
                success_count += 1
            except Exception as e:
                error_count += 1
            await asyncio.sleep(0.05)
            
        add_log(
            "INFO",
            "broadcast_completed",
            f"ارسال سراسری پایان یافت. موفق: {success_count}، ناموفق: {error_count}"
        )
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_send_all())
    loop.close()

@app.post("/broadcast")
@_requires_auth
def send_broadcast():
    text = request.form.get("message_text", "").strip()
    if not text:
        return redirect(url_for("index"))
        
    users = list_bot_users(limit=1000000)
    user_ids = [u["telegram_user_id"] for u in users]
    
    add_log(
        "INFO",
        "broadcast_started",
        f"ارسال پیام سراسری برای {len(user_ids)} کاربر آغاز شد."
    )
    
    threading.Thread(target=_send_broadcast_background, args=(text, user_ids), daemon=True).start()
    return redirect(url_for("index", saved="1"))


@app.post("/webhook/stripe")
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")

    settings = load_settings()
    active_webhook_secret = settings.get("stripe_webhook_secret") or STRIPE_WEBHOOK_SECRET
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, active_webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return "Invalid signature", 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        client_reference_id = session.get('client_reference_id')
        
        if client_reference_id:
            try:
                user_id_str, plan_code = client_reference_id.split("_")
                user_id = int(user_id_str)
                
                # Activate plan
                user = assign_user_plan(
                    user_id,
                    plan_code,
                    months=1,
                    note="Stripe Auto-Payment"
                )
                
                # Log it
                add_log(
                    "INFO",
                    "payment_success",
                    f"اشتراک {plan_code} از طریق استرایپ فعال شد.",
                    metadata={"telegram_user_id": user_id, "plan_code": plan_code}
                )
                
                # Send confirmation message
                import asyncio
                bot = Bot(token=BOT_TOKEN)
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    bot.send_message(
                        chat_id=user_id,
                        text=f"🎉 پرداخت شما با موفقیت انجام شد!\\n\\nاشتراک *{user['effective_plan']['name']}* برای شما تا ۳۰ روز آینده فعال گردید. از امکانات ربات لذت ببرید.",
                        parse_mode="Markdown"
                    )
                )
                loop.close()
                
            except Exception as e:
                add_log("ERROR", "webhook_process_error", str(e)[:300], metadata={"client_reference_id": client_reference_id})
                
    return jsonify(success=True), 200

def main() -> None:
    import os
    init_logs_db()
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
