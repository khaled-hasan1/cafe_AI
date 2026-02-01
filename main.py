from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, csv

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET_KEY_123"  # غيّرها لأي شي

# ====== إعداد المستخدمين (مؤقتاً محلياً) ======
# كل كافيه: username/password + file + plan
USERS = {
    "cafe1": {
        "password_hash": generate_password_hash("1234"),
        "file": "data/cafe1.csv",
        "plan": "platinum"  # basic / gold / platinum
    },
    "cafe2": {
        "password_hash": generate_password_hash("1234"),
        "file": "data/cafe2.csv",
        "plan": "basic"
    }
}

# ====== Helpers ======
def ensure_file(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("date,time,income,note\n")

def read_rows(path):
    ensure_file(path)
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            # حماية من صفوف قديمة/خربانة
            try:
                d = row.get("date","").strip()
                t = row.get("time","").strip()
                inc = float(row.get("income","0") or 0)
                note = (row.get("note","") or "").strip()
                if d:
                    rows.append({"date": d, "time": t, "income": inc, "note": note})
            except:
                continue
    return rows

def append_row(path, date, time_, income, note):
    ensure_file(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([date, time_, f"{float(income):.2f}", note])

def avg(values):
    return round(sum(values)/len(values), 2) if values else 0.0

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def now_time_str():
    return datetime.now().strftime("%H:%M")

def best_weak_time_bucket(rows):
    # تقسيم اليوم لفترات: Morning / Afternoon / Evening
    # بناءً على مجموع دخل كل فترة (اليوم الحالي فقط)
    today = today_str()
    trows = [x for x in rows if x["date"] == today and x["time"]]
    if not trows:
        return None

    buckets = {
        "morning": {"label_ar":"الصبح (8-11)", "label_en":"Morning (8-11)", "sum":0.0},
        "afternoon": {"label_ar":"الظهر/العصر (12-16)", "label_en":"Afternoon (12-16)", "sum":0.0},
        "evening": {"label_ar":"المساء (17-22)", "label_en":"Evening (17-22)", "sum":0.0},
    }

    for x in trows:
        try:
            h = int(x["time"].split(":")[0])
        except:
            continue
        if 8 <= h <= 11:
            buckets["morning"]["sum"] += x["income"]
        elif 12 <= h <= 16:
            buckets["afternoon"]["sum"] += x["income"]
        elif 17 <= h <= 22:
            buckets["evening"]["sum"] += x["income"]

    # أقل مجموع = أضعف فترة
    weak = min(buckets.items(), key=lambda kv: kv[1]["sum"])
    return weak[0], weak[1]

def suggestions(lang="ar"):
    # حلول أكثر (زي ما طلبت)
    if lang == "en":
        return [
            "Run a quick 1-hour offer (BOGO / 20% off).",
            "Push add-ons (dessert / extra shot / combo).",
            "Call regular customers (WhatsApp / stories).",
            "Adjust staff focus during peak time.",
            "Try a small sampling at the entrance."
        ]
    return [
        "اعمل عرض سريع ساعة (1+1 / خصم 20%).",
        "ركّز على الإضافات (حلويات / شوت زيادة / كومبو).",
        "ذكّر الزباين الدائمين (واتساب/ستوري).",
        "وزّع الشغل صح على ساعة الذروة.",
        "جرّب تذوق بسيط على باب المحل."
    ]

def plan_rules(plan):
    # basic: مرة باليوم (بدون وقت)
    # gold: مرتين باليوم
    # platinum: ثلاث مرات باليوم
    if plan == "basic":
        return 1
    if plan == "gold":
        return 2
    return 3

def is_limit_reached(rows, plan):
    limit = plan_rules(plan)
    today = today_str()
    count = len([x for x in rows if x["date"] == today])
    return count >= limit, count, limit

def compute_metrics(rows):
    # today income
    today = today_str()
    today_income = round(sum(x["income"] for x in rows if x["date"] == today), 2)

    # last 7 days avg (based on daily totals)
    daily = {}
    for x in rows:
        daily.setdefault(x["date"], 0.0)
        daily[x["date"]] += x["income"]

    dates_sorted = sorted(daily.keys())
    last7 = dates_sorted[-7:] if len(dates_sorted) >= 7 else dates_sorted
    last30 = dates_sorted[-30:] if len(dates_sorted) >= 30 else dates_sorted

    avg7 = avg([daily[d] for d in last7])
    avg30 = avg([daily[d] for d in last30])

    return today_income, avg7, avg30, daily

# ====== Auth ======
@app.route("/login", methods=["GET", "POST"])
def login():
    lang = request.args.get("lang") or session.get("lang") or "ar"
    session["lang"] = lang

    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()

        user = USERS.get(username)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("خطأ بالبيانات" if lang=="ar" else "Invalid credentials")
            return redirect(url_for("login", lang=lang))

        session["user"] = username
        return redirect(url_for("dashboard", lang=lang))

    return render_template("login.html", lang=lang)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def require_login():
    u = session.get("user")
    return u if u in USERS else None

# ====== Dashboard ======
@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("dashboard"))

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    user = require_login()
    if not user:
        return redirect(url_for("login"))

    lang = request.args.get("lang") or session.get("lang") or "ar"
    session["lang"] = lang

    user_conf = USERS[user]
    plan = user_conf["plan"]
    data_file = user_conf["file"]

    rows = read_rows(data_file)

    # حفظ إدخال جديد
    if request.method == "POST":
        # تحقق من limit حسب الاشتراك
        reached, count, limit = is_limit_reached(rows, plan)
        if reached:
            msg_ar = f"وصلت حد اشتراكك اليوم ({limit} مرات)."
            msg_en = f"You reached your daily plan limit ({limit} entries)."
            flash(msg_ar if lang=="ar" else msg_en)
            return redirect(url_for("dashboard", lang=lang))

        income = request.form.get("income","").strip()
        note = request.form.get("note","").strip()

        try:
            income_val = float(income)
        except:
            flash("دخل غير صحيح" if lang=="ar" else "Invalid income")
            return redirect(url_for("dashboard", lang=lang))

        # وقت وتاريخ تلقائي
        d = today_str()
        t = now_time_str()
        append_row(data_file, d, t, income_val, note)

        return redirect(url_for("dashboard", lang=lang))

    # Metrics
    today_income, avg7, avg30, daily = compute_metrics(rows)

    # تحليل ضعف الوقت (يعتمد على وجود time -> gold/platinum)
    weak_time = best_weak_time_bucket(rows)

    # جمل جاهزة
    tips = suggestions(lang)

    # آخر 10
    last10 = list(reversed(rows))[:10]

    # رسالة الاشتراك
    limit = plan_rules(plan)
    today_count = len([x for x in rows if x["date"] == today_str()])
    plan_msg_ar = f"اشتراكك: {plan} | اليوم سجلت {today_count} من {limit}"
    plan_msg_en = f"Plan: {plan} | Today entries {today_count}/{limit}"

    return render_template(
        "dashboard.html",
        lang=lang,
        user=user,
        plan=plan,
        plan_msg=(plan_msg_ar if lang=="ar" else plan_msg_en),
        today_income=today_income,
        avg7=avg7,
        avg30=avg30,
        tips=tips,
        weak_time=weak_time,
        last10=last10
    )

# ====== Change Password (اختياري بسيط) ======
@app.route("/change_password", methods=["GET","POST"])
def change_password():
    user = require_login()
    if not user:
        return redirect(url_for("login"))

    lang = request.args.get("lang") or session.get("lang") or "ar"
    session["lang"] = lang

    if request.method == "POST":
        oldp = request.form.get("old","").strip()
        newp = request.form.get("new","").strip()

        if not check_password_hash(USERS[user]["password_hash"], oldp):
            flash("كلمة المرور القديمة غلط" if lang=="ar" else "Wrong old password")
            return redirect(url_for("change_password", lang=lang))

        if len(newp) < 4:
            flash("خليها 4 أحرف/أرقام على الأقل" if lang=="ar" else "Min 4 chars")
            return redirect(url_for("change_password", lang=lang))

        USERS[user]["password_hash"] = generate_password_hash(newp)
        flash("تم تغيير كلمة المرور ✅" if lang=="ar" else "Password changed ✅")
        return redirect(url_for("dashboard", lang=lang))

    return render_template("change_password.html", lang=lang)

if __name__ == "__main__":
    # تشغيل على الشبكة عشان صاحبك يفتح من جهاز ثاني
    app.run(host="0.0.0.0", port=5000, debug=True)
