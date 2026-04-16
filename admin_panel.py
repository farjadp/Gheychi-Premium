import os
import tempfile
import zipfile
from functools import wraps
import asyncio
import threading
from telegram import Bot
import stripe
from config import STRIPE_WEBHOOK_SECRET, BOT_TOKEN

from flask import Flask, Response, jsonify, send_file, redirect, render_template_string, request, url_for

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
  <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {
      /* Midnight Purple & Blue Premium Theme */
      --bg:       #080A11;
      --bg-glow:  #15092A;
      --surface:  rgba(20, 22, 35, 0.65);
      --card:     rgba(30, 33, 50, 0.45);
      --border:   rgba(108, 138, 255, 0.15);
      --ink:      #f4f6fa;
      --muted:    #8b94b0;
      --accent:   #818cf8; /* Indigo accent */
      --accent2:  #c084fc; /* Purple accent */
      --accent3:  #f472b6; /* Pink accent */
      --green:    #34d399;
      --red:      #fb7185;
      --yellow:   #fbbf24;
      --radius:   20px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    
    body {
      font-family: "Vazirmatn", "Inter", system-ui, sans-serif;
      background: var(--bg);
      background-image: 
        radial-gradient(ellipse at 80% 0%, var(--bg-glow) 0%, transparent 40%),
        radial-gradient(ellipse at 10% 90%, rgba(30, 20, 60, 0.4) 0%, transparent 35%);
      background-size: cover;
      background-attachment: fixed;
      color: var(--ink);
      min-height: 100vh;
      font-weight: 400;
    }

    /* ── Sidebar ── */
    .sidebar {
      position: fixed; top: 0; right: 0;
      width: 250px; height: 100vh;
      background: var(--surface);
      backdrop-filter: blur(24px) saturate(180%);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      border-left: 1px solid var(--border);
      display: flex; flex-direction: column;
      padding: 30px 20px;
      z-index: 100;
      box-shadow: -10px 0 30px rgba(0,0,0,0.2);
    }
    .logo {
      display: flex; align-items: center; gap: 12px;
      padding: 0 8px 30px;
      margin-bottom: 24px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .logo-icon {
      width: 42px; height: 42px; border-radius: 12px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      display: flex; align-items: center; justify-content: center;
      font-size: 20px;
      box-shadow: 0 4px 15px rgba(192, 132, 252, 0.4);
    }
    .logo-text { font-weight: 800; font-size: 16px; line-height: 1.3; }
    .logo-text span { display: block; font-size: 12px; color: var(--muted); font-weight: 500; margin-top:2px; }
    .nav-item {
      display: flex; align-items: center; gap: 12px;
      padding: 12px 14px; border-radius: 12px;
      color: #9ba3be; font-size: 15px; font-weight: 600;
      cursor: pointer; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); margin-bottom: 4px;
      text-decoration: none; border: none; background: transparent; width: 100%; text-align: right;
    }
    .nav-item:hover {
      background: rgba(255, 255, 255, 0.04); color: var(--ink);
      transform: translateX(-4px);
    }
    .nav-item.active {
      background: linear-gradient(90deg, rgba(129, 140, 248, 0.15) 0%, rgba(192, 132, 252, 0.05) 100%);
      color: var(--accent);
      border-right: 3px solid var(--accent);
    }
    .nav-item .icon { font-size: 18px; width: 22px; text-align: center; }

    /* ── Main ── */
    .main { margin-right: 250px; padding: 40px; max-width: 1250px; }

    /* ── Topbar ── */
    .topbar {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 35px;
    }
    .page-title { font-size: 26px; font-weight: 800; letter-spacing: -0.02em; }
    .flash {
      display: flex; align-items: center; gap: 10px;
      background: rgba(52,211,153,.15); color: var(--green);
      border: 1px solid rgba(52,211,153,.25);
      border-radius: 12px; padding: 12px 20px; font-size: 14px; font-weight:600;
      backdrop-filter: blur(10px); box-shadow: 0 4px 20px rgba(52,211,153,0.1);
    }

    /* ── Stats ── */
    .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 20px; margin-bottom: 35px; }
    .stat-card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 24px;
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.18);
      transition: transform 0.25s ease, box-shadow 0.25s ease;
    }
    .stat-card:hover {
      transform: translateY(-5px);
      box-shadow: 0 12px 40px rgba(0,0,0,0.25);
      border-color: rgba(255,255,255,0.1);
    }
    .stat-card .label { font-size: 13px; color: var(--muted); margin-bottom: 10px; font-weight:600; }
    .stat-card .value { font-size: 38px; font-weight: 900; letter-spacing: -0.02em; }
    .stat-card .sub { font-size: 12px; color: var(--muted); margin-top: 6px; font-weight:500; }
    .stat-card.green .value { background: linear-gradient(90deg, #34d399, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .stat-card.red .value { background: linear-gradient(90deg, #fb7185, #f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .stat-card.blue .value { background: linear-gradient(90deg, #818cf8, #60a5fa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .stat-card.purple .value { background: linear-gradient(90deg, #c084fc, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

    /* ── Tabs ── */
    .tabs { display: flex; gap: 8px; margin-bottom: 30px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0; }
    .tab-btn {
      padding: 12px 22px; border-radius: 12px 12px 0 0; font-size: 15px;
      font-weight: 600; cursor: pointer; border: none; background: transparent;
      color: var(--muted); transition: all .2s; border-bottom: 3px solid transparent;
      margin-bottom: -1px; font-family: inherit;
    }
    .tab-btn.active { color: var(--ink); border-bottom-color: var(--accent); }
    .tab-btn:hover:not(.active) { color: var(--ink); background:rgba(255,255,255,0.02); }
    .tab-panel { display: none; animation: fadeIn 0.3s ease-in-out; }
    .tab-panel.active { display: block; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

    /* ── Grid ── */
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 20px; }

    /* ── Card ── */
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 28px;
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.15);
    }
    .card-title {
      font-size: 18px; font-weight: 700; margin-bottom: 24px;
      display: flex; align-items: center; gap: 10px;
    }
    .card-title .icon { font-size: 20px; }

    /* ── Form ── */
    .field { margin-bottom: 20px; }
    .field label { display: block; font-size: 14px; color: #a1a9c2; margin-bottom: 8px; font-weight: 600; }
    .field input, .field select, .field textarea {
      width: 100%; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08);
      color: var(--ink); border-radius: 12px; padding: 12px 16px;
      font-family: inherit; font-size: 15px; font-weight: 500; transition: all .2s ease;
    }
    .field input:focus, .field select:focus, .field textarea:focus {
      outline: none; border-color: var(--accent2); background: rgba(0,0,0,0.3);
      box-shadow: 0 0 0 3px rgba(192, 132, 252, 0.15);
    }
    .field textarea { min-height: 90px; resize: vertical; }
    .toggle-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .toggle-row:last-child { border-bottom: none; }
    .toggle-label { font-size: 15px; font-weight:600; }
    .toggle-sub { font-size: 13px; color: var(--muted); margin-top: 4px; font-weight:500; }
    
    /* iOS-style toggle */
    .toggle { position: relative; display: inline-block; width: 48px; height: 26px; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute; inset: 0; background: rgba(255,255,255,0.1);
      border-radius: 30px; cursor: pointer; transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .slider:before {
      content: ""; position: absolute;
      width: 20px; height: 20px; left: 3px; bottom: 3px;
      background: white; border-radius: 50%; transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }
    .toggle input:checked + .slider { background: linear-gradient(90deg, var(--accent), var(--accent2)); }
    .toggle input:checked + .slider:before { transform: translateX(22px); }
    
    .checks-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0 24px; }
    .check-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px; border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.06); font-size: 14px; font-weight:500; cursor: pointer;
      transition: all .2s; background: rgba(0,0,0,0.1);
    }
    .check-item:has(input:checked) { border-color: var(--accent); background: rgba(129, 140, 248, 0.1); }
    .check-item input { accent-color: var(--accent); width: 16px; height: 16px; cursor:pointer; }
    .btn {
      display: inline-flex; align-items: center; gap: 10px;
      padding: 12px 24px; border-radius: 12px; font-family: inherit;
      font-size: 15px; font-weight: 700; cursor: pointer; border: none;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: white; transition: all .25s ease;
      box-shadow: 0 4px 15px rgba(129, 140, 248, 0.3);
    }
    .btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(192, 132, 252, 0.4); }
    .btn-sm { padding: 8px 16px; font-size: 14px; border-radius: 10px; }

    /* ── Table ── */
    .table-wrap { overflow-x: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
    .table-wrap::-webkit-scrollbar { height: 6px; }
    .table-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
    table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 14px; font-weight:500; }
    thead th {
      text-align: right; padding: 14px 16px;
      color: var(--muted); font-size: 12px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .08em;
      border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.15);
    }
    thead th:first-child { border-top-right-radius: 12px; }
    thead th:last-child { border-top-left-radius: 12px; }
    tbody td {
      padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.04);
      vertical-align: top; line-height: 1.6;
    }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: rgba(255,255,255,0.02); }
    .cell-main { font-weight: 600; font-size: 15px; }
    .cell-sub { font-size: 13px; color: var(--muted); margin-top: 4px; font-weight: 500; }

    /* ── Badges ── */
    .badge {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 12px; border-radius: 999px;
      font-size: 12px; font-weight: 700;
      backdrop-filter: blur(8px);
    }
    .badge.INFO, .badge.ok { background: rgba(52,211,153,.15); color: var(--green); border: 1px solid rgba(52,211,153,.2); }
    .badge.ERROR, .badge.err { background: rgba(248,113,113,.15); color: var(--red); border: 1px solid rgba(248,113,113,.2);  }
    .badge.WARN { background: rgba(251,191,36,.15); color: var(--yellow); border: 1px solid rgba(251,191,36,.2);  }
    .badge.plan-free { background: rgba(122,128,153,.15); color: #a5accc; }
    .badge.plan-starter { background: rgba(52,211,153,.15); color: var(--green); }
    .badge.plan-standard { background: rgba(129,140,248,.15); color: var(--accent); }
    .badge.plan-pro { background: rgba(192,132,252,.15); color: var(--accent2); }

    /* ── Plan cards ── */
    .plan-card {
      background: linear-gradient(180deg, rgba(30,33,50,0.6) 0%, rgba(20,22,35,0.4) 100%);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: var(--radius); padding: 28px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.2);
      transition: transform 0.3s ease;
    }
    .plan-card:hover { transform: translateY(-4px); border-color: rgba(255,255,255,0.1); }
    .plan-name { font-size: 20px; font-weight: 800; margin-bottom: 8px; }
    .plan-price { font-size: 32px; font-weight: 900; background: linear-gradient(90deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 6px; }
    .plan-price span { font-size: 15px; font-weight: 500; -webkit-text-fill-color: var(--muted); }
    .plan-desc { font-size: 14px; color: var(--muted); margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.06); line-height:1.6; }
    .plan-rule { font-size: 14px; color: #b4bada; padding: 6px 0; display: flex; align-items: center; gap: 8px; font-weight:500; }
    .plan-rule::before { content: "•"; color: var(--accent2); font-size: 18px; line-height: 1; opacity: 0.8; }

    /* ── URL cell ── */
    .url-cell { max-width: 250px; word-break: break-all; color: var(--muted); font-size: 13px; font-family: monospace; }
    .url-cell a { color: var(--accent); text-decoration: none; }
    .url-cell a:hover { text-decoration: underline; }

    /* ── Avatar ── */
    .avatar {
      width: 42px; height: 42px; border-radius: 12px;
      background: linear-gradient(135deg, rgba(129,140,248,0.2), rgba(192,132,252,0.2));
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 18px; color: var(--ink);
      border: 1px solid rgba(192,132,252,0.2);
    }
    .user-cell { display: flex; align-items: center; gap: 14px; }

    @media (max-width: 900px) {
      .sidebar { width: 80px; padding: 24px 10px; }
      .logo-text, .nav-item span:not(.icon) { display: none; }
      .main { margin-right: 80px; padding: 24px; }
    }
    @media (max-width: 600px) {
      .stats { grid-template-columns: 1fr 1fr; }
      .checks-grid { grid-template-columns: 1fr; }
      .grid-2, .grid-3 { grid-template-columns: 1fr; }
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
              
              <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); border-radius:12px; padding:16px; margin-bottom:24px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px;">
                <div>
                  <div style="font-size:15px; font-weight:700; color:var(--ink); margin-bottom:4px;">پشتیبان‌گیری سخت‌افزاری (کدها + دیتابیس)</div>
                  <div style="font-size:13px; color:var(--muted);">تمام فایل‌های پایتون، دیتابیس sqlite و JSON ها در یک فایل فشرده امن (بدون پکیج‌های حجیم) دریافت می‌شود.</div>
                </div>
                <a href="/backup/download" class="btn" style="background:linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05)); border:1px solid rgba(255,255,255,0.1); color:var(--ink); box-shadow:none;"><span class="icon">📦</span> ایجاد و دانلود فایل ZIP پشتیبان</a>
              </div>
              
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
        <div class="card" style="grid-column: 1 / -1;">
          <div class="card-title" style="display:flex; justify-content:space-between; align-items:center; width:100%;">
            <span><span class="icon">📦</span> تنظیمات و محدودیت پکیج‌ها</span>
            <button type="button" class="btn btn-sm" onclick="toggleJsonEditor()" style="background:rgba(255,255,255,0.1); color:var(--muted); box-shadow:none;">کد خام (JSON)</button>
          </div>
          
          <form method="post" action="{{ url_for('update_plans') }}" id="plans-form">
            <!-- Visual Editor Area -->
            <div id="visual-editor">
              <div class="tabs" id="plan-tabs" style="margin-bottom:20px;"></div>
              <div id="plan-editor-content"></div>
            </div>

            <!-- RAW JSON Editor (Hidden by default) -->
            <div id="raw-json-editor" style="display:none; margin-top:20px;">
              <p style="font-size:13px; color:var(--muted); margin-bottom:15px; background:rgba(251,191,36,0.1); padding:10px; border-radius:8px; color:var(--yellow); border:1px solid rgba(251,191,36,0.2);">
                ⚠️ اخطار: اینجا یک محیط پیشرفته است. اگر نمیدانید چه میکنید، از ظاهر گرافیکی استفاده کنید.
              </p>
              <div class="field">
                <textarea id="plans-json-textarea" name="plans_json" style="font-family: monospace; direction: ltr; text-align: left; min-height: 400px; line-height: 1.5; background:#0b0d14; color:#a5acca; padding:15px; border-radius:12px; width:100%; border:1px solid rgba(255,255,255,0.05);">{{ plans_json_str }}</textarea>
              </div>
            </div>

            <div style="margin-top: 25px; border-top: 1px solid rgba(255,255,255,0.05); padding-top:20px;">
              <button class="btn" type="submit">💾 ذخیره تمامی اطلاعات پکیج‌ها</button>
            </div>
          </form>
        </div>
        
        {% for plan in plans %}
        <!-- Visual Previews -->
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

<script>
  let rawJsonData = {};
  
  try {
    const textarea = document.getElementById('plans-json-textarea');
    rawJsonData = JSON.parse(textarea.value);
  } catch (e) {
    console.error("Invalid JSON string at startup", e);
  }

  let currentPlanId = Object.keys(rawJsonData)[0] || null;

  function toggleJsonEditor() {
    const raw = document.getElementById('raw-json-editor');
    const vis = document.getElementById('visual-editor');
    if(raw.style.display === 'none') {
      raw.style.display = 'block';
      vis.style.display = 'none';
      syncVisualToJson(); // push visual updates to textarea before showing
    } else {
      raw.style.display = 'none';
      vis.style.display = 'block';
      // Load from textarea
      try {
        rawJsonData = JSON.parse(document.getElementById('plans-json-textarea').value);
        renderVisualEditor();
      } catch(e) {
        alert("فرمت JSON وارد شده نامعتبر است! نمیتوان به حالت گرافیکی برگشت.");
        raw.style.display = 'block';
        vis.style.display = 'none';
      }
    }
  }

  function syncVisualToJson() {
    const textarea = document.getElementById('plans-json-textarea');
    textarea.value = JSON.stringify(rawJsonData, null, 2);
  }

  function handleDataChange() {
    syncVisualToJson();
  }

  function switchPlan(planId) {
    currentPlanId = planId;
    renderVisualEditor();
  }

  function addRule(planId) {
    if(!rawJsonData[planId].rules) rawJsonData[planId].rules = [];
    rawJsonData[planId].rules.push({ platform: "Twitter/X", limit: null, period: "month" });
    handleDataChange();
    renderVisualEditor();
  }

  function removeRule(planId, idx) {
    rawJsonData[planId].rules.splice(idx, 1);
    handleDataChange();
    renderVisualEditor();
  }

  function renderVisualEditor() {
    const tabsContainer = document.getElementById('plan-tabs');
    const contentContainer = document.getElementById('plan-editor-content');
    
    // Render Tabs
    tabsContainer.innerHTML = '';
    Object.keys(rawJsonData).forEach(planId => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tab-btn ' + (planId === currentPlanId ? 'active' : '');
      const name = rawJsonData[planId].name || planId;
      btn.innerHTML = `<span class="icon">📦</span> ${name}`;
      btn.onclick = () => switchPlan(planId);
      tabsContainer.appendChild(btn);
    });

    if(!currentPlanId || !rawJsonData[currentPlanId]) return;

    // Render Content for currentPlanId
    const plan = rawJsonData[currentPlanId];
    
    let html = `
      <div style="background:rgba(0,0,0,0.15); padding:24px; border-radius:16px; border:1px solid rgba(255,255,255,0.05);">
        <div class="grid-2" style="margin-bottom:15px;">
          <div class="field" style="margin-bottom:0;">
            <label>شناسه سیستمی (غیرقابل تغییر)</label>
            <input type="text" value="${currentPlanId}" disabled style="opacity:0.5;">
          </div>
          <div class="field" style="margin-bottom:0;">
            <label>نام نمایشی (فارسی)</label>
            <input type="text" value="${plan.name || ''}" onchange="rawJsonData['${currentPlanId}'].name = this.value; renderVisualEditor(); handleDataChange();">
          </div>
        </div>
        <div class="field">
          <label>قیمت ماهانه (دلار) - اگر 0 باشد یعنی رایگان است</label>
          <input type="number" value="${plan.price_usd || 0}" onchange="rawJsonData['${currentPlanId}'].price_usd = parseInt(this.value)||0; handleDataChange();">
        </div>
        <div class="field">
          <label>توضیحات پکیج</label>
          <input type="text" value="${plan.description || ''}" onchange="rawJsonData['${currentPlanId}'].description = this.value; handleDataChange();">
        </div>
        
        <div style="margin-top:30px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
            <label style="font-size:15px; font-weight:700; color:var(--accent);">محدودیت پلتفرم‌ها (Rules)</label>
            <button type="button" class="btn btn-sm" onclick="addRule('${currentPlanId}')" style="background:rgba(52,211,153,0.15); color:var(--green);"><span class="icon">+</span> افزودن شبکه‌اجتماعی</button>
          </div>
    `;

    if (plan.rules && plan.rules.length > 0) {
      plan.rules.forEach((rule, idx) => {
        html += `
          <div style="background:rgba(255,255,255,0.02); padding:16px; border-radius:12px; border:1px solid rgba(255,255,255,0.04); margin-bottom:12px; display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end;">
            <div class="field" style="margin-bottom:0; flex:1; min-width:140px;">
              <label>کدام پلتفرم؟</label>
              <select onchange="rawJsonData['${currentPlanId}'].rules[${idx}].platform = this.value; handleDataChange();">
                <option value="Twitter/X" ${rule.platform === 'Twitter/X' ? 'selected' : ''}>Twitter/X</option>
                <option value="Instagram" ${rule.platform === 'Instagram' ? 'selected' : ''}>Instagram</option>
                <option value="YouTube" ${rule.platform === 'YouTube' ? 'selected' : ''}>YouTube</option>
                <option value="SoundCloud" ${rule.platform === 'SoundCloud' ? 'selected' : ''}>SoundCloud</option>
                <option value="TikTok" ${rule.platform === 'TikTok' ? 'selected' : ''}>TikTok</option>
                <option value="PornHub" ${rule.platform === 'PornHub' ? 'selected' : ''}>PornHub</option>
                <option value="Facebook" ${rule.platform === 'Facebook' ? 'selected' : ''}>Facebook</option>
                <option value="Vimeo" ${rule.platform === 'Vimeo' ? 'selected' : ''}>Vimeo</option>
                <option value="RadioJavan" ${rule.platform === 'RadioJavan' ? 'selected' : ''}>RadioJavan</option>
                <option value="Twitch" ${rule.platform === 'Twitch' ? 'selected' : ''}>Twitch</option>
                <option value="و بیش از ۱۰۰۰ سایت دیگر" ${rule.platform === 'و بیش از ۱۰۰۰ سایت دیگر' ? 'selected' : ''}>سایر سایت‌ها</option>
              </select>
            </div>
            <div class="field" style="margin-bottom:0; width:100px;">
              <label>تعداد (خالی=بی‌نهایت)</label>
              <input type="number" placeholder="بی‌نهایت" value="${rule.limit === null ? '' : rule.limit}" onchange="rawJsonData['${currentPlanId}'].rules[${idx}].limit = this.value === '' ? null : parseInt(this.value); handleDataChange();">
            </div>
            <div class="field" style="margin-bottom:0; width:120px;">
              <label>بازه زمانی</label>
              <select onchange="rawJsonData['${currentPlanId}'].rules[${idx}].period = this.value; handleDataChange();">
                <option value="month" ${rule.period === 'month' ? 'selected' : ''}>در ماه</option>
                <option value="week" ${rule.period === 'week' ? 'selected' : ''}>در هفته</option>
                <option value="day" ${rule.period === 'day' ? 'selected' : ''}>در روز</option>
              </select>
            </div>
            <div class="field" style="margin-bottom:0; width:120px;">
              <label>سقف زمان ویدئو (ثانیه)</label>
              <input type="number" placeholder="بدون محدودیت" value="${rule.max_duration_seconds || ''}" onchange="rawJsonData['${currentPlanId}'].rules[${idx}].max_duration_seconds = this.value === '' ? null : parseInt(this.value); handleDataChange();">
            </div>
            <button type="button" class="btn btn-sm" onclick="removeRule('${currentPlanId}', ${idx})" style="background:rgba(248,113,113,0.15); color:var(--red); padding:10px; height:42px;"><span class="icon">🗑️</span></button>
          </div>
        `;
      });
    } else {
      html += `<div style="padding:15px; text-align:center; color:var(--muted); font-size:14px; border:1px dashed rgba(255,255,255,0.1); border-radius:10px;">هیچ محدودیتی هنوز اضافه نشده. (یعنی دسترسی نامحدود است)</div>`;
    }
    
    html += `</div></div>`;
    contentContainer.innerHTML = html;
  }

  // Init visual editor on page load
  document.addEventListener('DOMContentLoaded', () => {
    // Only init if we are on plans tab
    renderVisualEditor();
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


@app.get("/backup/download")
@requires_auth
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
                            
        add_log("INFO", "system_backup", "یک نسخه پشتیبان کامل از سیستم استخراج شد.")
        return send_file(zip_path, as_attachment=True, download_name='gheychi_premium_backup.zip', mimetype='application/zip')
    except Exception as e:
        return f"Backup failed: {str(e)}", 500

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
