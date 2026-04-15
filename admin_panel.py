from functools import wraps

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
  <title>پنل مدیریت Gheychi Premium</title>
  <style>
    :root {
      --bg: #f4efe7;
      --surface: #fffdf8;
      --ink: #172121;
      --muted: #5f6b66;
      --accent: #d68c45;
      --accent-strong: #9c6644;
      --line: #e7dccd;
      --ok: #386641;
      --warn: #bc6c25;
      --hero: #132a13;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "SF Pro Display", "Helvetica Neue", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(214, 140, 69, 0.24), transparent 28%),
        linear-gradient(180deg, #f7f1e7, #efe4d2);
      color: var(--ink);
    }
    .wrap { max-width: 1320px; margin: 0 auto; padding: 28px 20px 48px; }
    .hero {
      background: linear-gradient(135deg, rgba(19,42,19,.96), rgba(56,102,65,.86));
      color: white; border-radius: 30px; padding: 28px; margin-bottom: 22px;
      box-shadow: 0 18px 50px rgba(19,42,19,.18);
    }
    .hero h1 { margin: 0 0 8px; font-size: 34px; }
    .hero p { margin: 0; color: rgba(255,255,255,.82); }
    .stats {
      display: grid; grid-template-columns: repeat(4, 1fr);
      gap: 12px; margin-top: 18px;
    }
    .stat {
      background: rgba(255,255,255,.12);
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 18px;
      padding: 16px;
    }
    .stat strong { display: block; font-size: 24px; margin-bottom: 6px; }
    .layout {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 20px;
      align-items: start;
    }
    .stack { display: grid; gap: 20px; }
    .card {
      background: rgba(255,253,248,.9);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(231,220,205,.95);
      border-radius: 24px;
      padding: 22px;
      box-shadow: 0 10px 30px rgba(70,52,33,.08);
    }
    h2 { margin: 0 0 16px; font-size: 20px; }
    h3 { margin: 0 0 12px; font-size: 16px; }
    label { display: block; margin-bottom: 8px; font-weight: 600; }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 14px;
      padding: 12px 14px;
      font: inherit;
      margin-bottom: 14px;
    }
    textarea { min-height: 92px; resize: vertical; }
    .checks { display: grid; gap: 10px; margin: 14px 0 18px; }
    .checks label, .switch { font-weight: 500; }
    .switch { display: flex; gap: 10px; align-items: center; margin-bottom: 18px; }
    .switch input, .checks input { width: auto; margin: 0; }
    button {
      border: 0; border-radius: 999px; padding: 12px 18px; font: inherit; cursor: pointer;
      color: white; background: linear-gradient(135deg, var(--accent), var(--accent-strong));
    }
    .flash {
      background: rgba(56,102,65,.1); color: var(--ok); border: 1px solid rgba(56,102,65,.18);
      border-radius: 16px; padding: 12px 14px; margin-bottom: 16px;
    }
    .plans { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
    .plan {
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 16px;
      background: rgba(255,255,255,.55);
    }
    .plan strong { font-size: 18px; }
    .price { color: var(--hero); font-weight: 700; margin: 8px 0 10px; }
    .rule { color: var(--muted); margin: 6px 0; font-size: 14px; }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      text-align: right; padding: 12px 10px;
      border-bottom: 1px solid var(--line); vertical-align: top;
    }
    th { color: var(--muted); font-size: 13px; }
    .badge {
      display: inline-flex; padding: 5px 10px; border-radius: 999px;
      font-size: 12px; font-weight: 700;
    }
    .badge.INFO { background: rgba(56,102,65,.12); color: var(--ok); }
    .badge.ERROR { background: rgba(188,108,37,.13); color: var(--warn); }
    .muted { color: var(--muted); }
    .tiny { font-size: 13px; color: var(--muted); }
    .url { max-width: 280px; word-break: break-all; }
    .usage-line { margin-bottom: 6px; font-size: 13px; color: var(--muted); }
    @media (max-width: 1080px) {
      .layout { grid-template-columns: 1fr; }
      .stats { grid-template-columns: repeat(2, 1fr); }
      .plans { grid-template-columns: 1fr; }
    }
    @media (max-width: 700px) {
      .stats { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>پنل مدیریت Gheychi Premium</h1>
      <p>مدیریت محدودیت‌ها، پلن‌های اشتراک، کاربران و لاگ‌های سرویس از یک نقطه.</p>
      <div class="stats">
        <div class="stat"><strong>{{ stats.total_logs }}</strong><span>کل رویدادها</span></div>
        <div class="stat"><strong>{{ stats.errors }}</strong><span>خطاها</span></div>
        <div class="stat"><strong>{{ stats.users }}</strong><span>کاربران ثبت‌شده</span></div>
        <div class="stat"><strong>{{ stats.paid_users }}</strong><span>اشتراک فعال پولی</span></div>
      </div>
    </section>

    {% if saved %}
      <div class="flash">تنظیمات یا اشتراک کاربر با موفقیت ذخیره شد.</div>
    {% endif %}

    <div class="layout">
      <div class="stack">
        <section class="card">
          <h2>تنظیمات سرویس</h2>
          <form method="post" action="{{ url_for('update_settings') }}">
            <label for="max_file_size_mb">حداکثر حجم فایل برای ارسال</label>
            <input id="max_file_size_mb" name="max_file_size_mb" type="number" min="1" max="2000" value="{{ settings.max_file_size_mb }}">

            <label class="switch">
              <input type="checkbox" name="downloads_enabled" value="1" {% if settings.downloads_enabled %}checked{% endif %}>
              فعال بودن دانلود
            </label>

            <div class="checks">
              {% for platform in all_platforms %}
                <label>
                  <input type="checkbox" name="allowed_platforms" value="{{ platform }}" {% if platform in settings.allowed_platforms %}checked{% endif %}>
                  {{ platform }}
                </label>
              {% endfor %}
            </div>

            <button type="submit">ذخیره تنظیمات</button>
          </form>
          <p class="tiny">آخرین به‌روزرسانی: {{ settings.updated_at }}</p>
        </section>

        <section class="card">
          <h2>اختصاص اشتراک</h2>
          <form method="post" action="{{ url_for('assign_subscription') }}">
            <label for="telegram_user_id">Telegram User ID</label>
            <input id="telegram_user_id" name="telegram_user_id" type="number" required>

            <label for="plan_code">پلن</label>
            <select id="plan_code" name="plan_code">
              {% for plan in plans %}
                <option value="{{ plan.code }}">{{ plan.name }} - ${{ plan.price_usd }}/ماه</option>
              {% endfor %}
            </select>

            <label for="months">تعداد ماه</label>
            <input id="months" name="months" type="number" min="1" value="1">

            <label for="assigned_note">یادداشت</label>
            <textarea id="assigned_note" name="assigned_note" placeholder="مثلاً پرداخت Stripe / رسید دستی"></textarea>

            <button type="submit">ثبت یا تمدید اشتراک</button>
          </form>
        </section>
      </div>

      <div class="stack">
        <section class="card">
          <h2>کاتالوگ پلن‌ها</h2>
          <div class="plans">
            {% for plan in plans %}
              <div class="plan">
                <strong>{{ plan.name }}</strong>
                <div class="price">${{ plan.price_usd }}/ماه</div>
                <div class="tiny">{{ plan.description }}</div>
                <div style="margin-top: 10px;">
                  {% for rule in plan.rules %}
                    <div class="rule">{{ format_rule(rule) }}</div>
                  {% endfor %}
                </div>
              </div>
            {% endfor %}
          </div>
        </section>

        <section class="card">
          <h2>کاربران و اشتراک‌ها</h2>
          <table>
            <thead>
              <tr>
                <th>کاربر</th>
                <th>پلن ثبت‌شده</th>
                <th>پلن فعال</th>
                <th>انقضا</th>
                <th>مصرف فعلی</th>
              </tr>
            </thead>
            <tbody>
              {% for user in users %}
                <tr>
                  <td>
                    <div><strong>{{ user.first_name or '-' }}</strong></div>
                    <div class="tiny">@{{ user.username or '-' }}</div>
                    <div class="tiny">{{ user.telegram_user_id }}</div>
                  </td>
                  <td>
                    <div>{{ user.assigned_plan.name }}</div>
                    <div class="tiny">{{ user.assigned_note or '' }}</div>
                  </td>
                  <td>
                    <div>{{ user.effective_plan.name }}</div>
                    <div class="tiny">{% if user.is_subscription_active %}فعال{% else %}منقضی شده و به رایگان برگشته{% endif %}</div>
                  </td>
                  <td>{{ user.plan_expires_at or 'نامحدود' }}</td>
                  <td>
                    {% for line in user.usage_lines %}
                      <div class="usage-line">{{ line }}</div>
                    {% endfor %}
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </section>

        <section class="card">
          <h2>لاگ‌ها</h2>
          <table>
            <thead>
              <tr>
                <th>زمان</th>
                <th>سطح</th>
                <th>رویداد</th>
                <th>شرح</th>
                <th>پلتفرم</th>
                <th>لینک</th>
              </tr>
            </thead>
            <tbody>
              {% for log in logs %}
                <tr>
                  <td>{{ log.created_at }}</td>
                  <td><span class="badge {{ log.level }}">{{ log.level }}</span></td>
                  <td>{{ log.event_type }}</td>
                  <td>{{ log.message }}</td>
                  <td>{{ log.platform or "-" }}</td>
                  <td class="url">{{ log.url or "-" }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
</body>
</html>
"""


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

    stats = {
        "total_logs": len(logs),
        "errors": sum(1 for item in logs if item["level"] == "ERROR"),
        "users": len(users),
        "paid_users": sum(1 for user in users if user["effective_plan_code"] != "free"),
    }
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
    )


@app.post("/settings")
@_requires_auth
def update_settings():
    selected_platforms = request.form.getlist("allowed_platforms")
    settings = save_settings(
        {
            "max_file_size_mb": request.form.get("max_file_size_mb", 50),
            "downloads_enabled": request.form.get("downloads_enabled") == "1",
            "allowed_platforms": selected_platforms,
        }
    )
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


def main() -> None:
    init_logs_db()
    app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()
