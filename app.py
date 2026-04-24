from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date
import calendar
import json
from io import BytesIO
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

app = Flask(__name__)
app.secret_key = "cambia_esto_por_una_clave_secreta_larga"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "subsy_db"
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesión primero.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def get_user_subscriptions(user_id, category_filter=None, status_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT * FROM subscriptions
        WHERE user_id = %s
    """
    params = [user_id]

    if category_filter and category_filter != "all":
        query += " AND category = %s"
        params.append(category_filter)

    if status_filter == "active":
        query += " AND is_active = 1"
    elif status_filter == "inactive":
        query += " AND is_active = 0"

    query += " ORDER BY is_active DESC, renewal_day ASC, created_at DESC"

    cursor.execute(query, tuple(params))
    subs = cursor.fetchall()

    cursor.close()
    conn.close()
    return subs


def get_subscription_by_id(sub_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM subscriptions
        WHERE id = %s AND user_id = %s
    """, (sub_id, user_id))

    sub = cursor.fetchone()

    cursor.close()
    conn.close()
    return sub


def get_distinct_categories(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT category
        FROM subscriptions
        WHERE user_id = %s
        ORDER BY category ASC
    """, (user_id,))

    categories = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()
    return categories


def calculate_monthly_total(subscriptions):
    total = 0

    for sub in subscriptions:
        if not sub["is_active"]:
            continue

        if sub["billing_cycle"] == "monthly":
            total += float(sub["price"])
        elif sub["billing_cycle"] == "yearly":
            total += float(sub["price"]) / 12

    return round(total, 2)


def calculate_annual_total(subscriptions):
    total = 0

    for sub in subscriptions:
        if not sub["is_active"]:
            continue

        if sub["billing_cycle"] == "monthly":
            total += float(sub["price"]) * 12
        elif sub["billing_cycle"] == "yearly":
            total += float(sub["price"])

    return round(total, 2)


def get_upcoming_alerts(subscriptions):
    today = date.today()
    today_day = today.day
    alerts = []

    for sub in subscriptions:
        if not sub["is_active"]:
            continue

        renewal_day = int(sub["renewal_day"])
        days_left = renewal_day - today_day

        if days_left < 0:
            days_left += 30

        if 0 <= days_left <= 7:
            alerts.append({
                "id": sub["id"],
                "name": sub["name"],
                "price": float(sub["price"]),
                "renewal_day": renewal_day,
                "days_left": days_left,
                "color": sub["color"],
                "icon": sub["icon"]
            })

    alerts.sort(key=lambda x: x["days_left"])
    return alerts


def build_calendar_data(subscriptions, year, month):
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)
    month_name = calendar.month_name[month]
    _, last_day_of_month = calendar.monthrange(year, month)

    payments_by_day = {}

    for sub in subscriptions:
        if not sub["is_active"]:
            continue

        day = sub["renewal_day"]

        if day < 1:
            day = 1

        if day > last_day_of_month:
            day = last_day_of_month

        if day not in payments_by_day:
            payments_by_day[day] = []

        payments_by_day[day].append({
            "name": sub["name"],
            "price": float(sub["price"]),
            "billing_cycle": sub["billing_cycle"],
            "color": sub["color"],
            "icon": sub["icon"]
        })

    return {
        "weeks": month_days,
        "payments_by_day": payments_by_day,
        "month_name": month_name,
        "year": year,
        "month": month
    }


def build_chart_data(subscriptions):
    data = []

    for sub in subscriptions:
        if not sub["is_active"]:
            continue

        if sub["billing_cycle"] == "monthly":
            value = float(sub["price"])
        else:
            value = round(float(sub["price"]) / 12, 2)

        data.append({
            "name": sub["name"],
            "value": value,
            "color": sub["color"]
        })

    data.sort(key=lambda x: x["value"], reverse=True)
    return data


def build_annual_months_data(subscriptions):
    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    monthly_total = calculate_monthly_total(subscriptions)

    data = []

    for month in months:
        data.append({
            "month": month,
            "total": monthly_total
        })

    return data


def build_category_summary(subscriptions):
    summary = {}

    for sub in subscriptions:
        if not sub["is_active"]:
            continue

        category = sub["category"]

        if sub["billing_cycle"] == "monthly":
            monthly_cost = float(sub["price"])
        else:
            monthly_cost = float(sub["price"]) / 12

        if category not in summary:
            summary[category] = 0

        summary[category] += monthly_cost

    result = []

    for category, total in summary.items():
        result.append({
            "category": category,
            "monthly": round(total, 2),
            "annual": round(total * 12, 2)
        })

    result.sort(key=lambda x: x["monthly"], reverse=True)
    return result


@app.context_processor
def inject_notifications():
    if "user_id" not in session:
        return {
            "notification_count": 0,
            "notification_alerts": []
        }

    subscriptions = get_user_subscriptions(session["user_id"])
    alerts = get_upcoming_alerts(subscriptions)

    return {
        "notification_count": len(alerts),
        "notification_alerts": alerts
    }


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        if not username or not email or not password:
            flash("Completa todos los campos.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users (username, email, password)
                VALUES (%s, %s, %s)
            """, (username, email, hashed_password))

            conn.commit()

            cursor.close()
            conn.close()

            flash("Cuenta creada correctamente. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))

        except Error:
            flash("Ese email ya existe o ha ocurrido un error.", "danger")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Bienvenido de nuevo.", "success")
            return redirect(url_for("dashboard"))

        flash("Credenciales incorrectas.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    category_filter = request.args.get("category", "all")
    status_filter = request.args.get("status", "all")

    subscriptions = get_user_subscriptions(
        session["user_id"],
        category_filter=category_filter,
        status_filter=status_filter
    )

    all_subscriptions = get_user_subscriptions(session["user_id"])

    monthly_total = calculate_monthly_total(all_subscriptions)
    annual_total = calculate_annual_total(all_subscriptions)
    alerts = get_upcoming_alerts(all_subscriptions)
    categories = get_distinct_categories(session["user_id"])
    chart_data = build_chart_data(all_subscriptions)

    active_count = sum(1 for s in all_subscriptions if s["is_active"])
    inactive_count = sum(1 for s in all_subscriptions if not s["is_active"])

    return render_template(
        "dashboard.html",
        subscriptions=subscriptions,
        monthly_total=monthly_total,
        annual_total=annual_total,
        alerts=alerts,
        categories=categories,
        current_category=category_filter,
        current_status=status_filter,
        active_count=active_count,
        inactive_count=inactive_count,
        chart_data=json.dumps(chart_data, ensure_ascii=False)
    )


@app.route("/add-subscription", methods=["GET", "POST"])
@login_required
def add_subscription():
    if request.method == "POST":
        name = request.form["name"].strip()
        category = request.form["category"].strip()
        price = request.form["price"].strip()
        billing_cycle = request.form["billing_cycle"].strip()
        renewal_day = request.form["renewal_day"].strip()
        start_date = request.form["start_date"].strip()
        notes = request.form["notes"].strip()
        color = request.form["color"].strip() or "#38bdf8"
        icon = request.form["icon"].strip() or "📺"

        if not name or not price or not renewal_day:
            flash("Completa los campos obligatorios.", "danger")
            return redirect(url_for("add_subscription"))

        try:
            price = float(price)
            renewal_day = int(renewal_day)

            if renewal_day < 1 or renewal_day > 31:
                raise ValueError

        except ValueError:
            flash("Precio o día de renovación no válidos.", "danger")
            return redirect(url_for("add_subscription"))

        if not category:
            category = "Streaming"

        if not start_date:
            start_date = None

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO subscriptions (
                user_id, name, category, price, billing_cycle,
                renewal_day, start_date, notes, is_active, color, icon
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session["user_id"], name, category, price, billing_cycle,
            renewal_day, start_date, notes, 1, color, icon
        ))

        conn.commit()

        cursor.close()
        conn.close()

        flash("Suscripción añadida correctamente.", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_subscription.html")


@app.route("/edit-subscription/<int:sub_id>", methods=["GET", "POST"])
@login_required
def edit_subscription(sub_id):
    subscription = get_subscription_by_id(sub_id, session["user_id"])

    if not subscription:
        flash("Suscripción no encontrada.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form["name"].strip()
        category = request.form["category"].strip()
        price = request.form["price"].strip()
        billing_cycle = request.form["billing_cycle"].strip()
        renewal_day = request.form["renewal_day"].strip()
        start_date = request.form["start_date"].strip()
        notes = request.form["notes"].strip()
        color = request.form["color"].strip() or "#38bdf8"
        icon = request.form["icon"].strip() or "📺"
        is_active = 1 if request.form.get("is_active") == "1" else 0

        if not name or not price or not renewal_day:
            flash("Completa los campos obligatorios.", "danger")
            return redirect(url_for("edit_subscription", sub_id=sub_id))

        try:
            price = float(price)
            renewal_day = int(renewal_day)

            if renewal_day < 1 or renewal_day > 31:
                raise ValueError

        except ValueError:
            flash("Precio o día de renovación no válidos.", "danger")
            return redirect(url_for("edit_subscription", sub_id=sub_id))

        if not category:
            category = "Streaming"

        if not start_date:
            start_date = None

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE subscriptions
            SET name = %s,
                category = %s,
                price = %s,
                billing_cycle = %s,
                renewal_day = %s,
                start_date = %s,
                notes = %s,
                is_active = %s,
                color = %s,
                icon = %s
            WHERE id = %s AND user_id = %s
        """, (
            name, category, price, billing_cycle, renewal_day,
            start_date, notes, is_active, color, icon,
            sub_id, session["user_id"]
        ))

        conn.commit()

        cursor.close()
        conn.close()

        flash("Suscripción actualizada correctamente.", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_subscription.html", subscription=subscription)


@app.route("/toggle-subscription/<int:sub_id>", methods=["POST"])
@login_required
def toggle_subscription(sub_id):
    subscription = get_subscription_by_id(sub_id, session["user_id"])

    if not subscription:
        flash("Suscripción no encontrada.", "danger")
        return redirect(url_for("dashboard"))

    new_status = 0 if subscription["is_active"] else 1

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE subscriptions
        SET is_active = %s
        WHERE id = %s AND user_id = %s
    """, (new_status, sub_id, session["user_id"]))

    conn.commit()

    cursor.close()
    conn.close()

    flash("Estado actualizado correctamente.", "success")
    return redirect(url_for("dashboard"))


@app.route("/delete-subscription/<int:sub_id>", methods=["POST"])
@login_required
def delete_subscription(sub_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM subscriptions
        WHERE id = %s AND user_id = %s
    """, (sub_id, session["user_id"]))

    conn.commit()

    cursor.close()
    conn.close()

    flash("Suscripción eliminada.", "info")
    return redirect(url_for("dashboard"))


@app.route("/calendar")
@login_required
def subscription_calendar():
    today = date.today()
    year = request.args.get("year", type=int, default=today.year)
    month = request.args.get("month", type=int, default=today.month)

    subscriptions = get_user_subscriptions(session["user_id"])
    cal_data = build_calendar_data(subscriptions, year, month)

    prev_month = month - 1
    prev_year = year

    if prev_month < 1:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year

    if next_month > 12:
        next_month = 1
        next_year += 1

    return render_template(
        "calendar.html",
        cal_data=cal_data,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year
    )


@app.route("/annual")
@login_required
def annual_view():
    subscriptions = get_user_subscriptions(session["user_id"])

    annual_total = calculate_annual_total(subscriptions)
    monthly_total = calculate_monthly_total(subscriptions)
    annual_months = build_annual_months_data(subscriptions)
    category_summary = build_category_summary(subscriptions)

    return render_template(
        "annual.html",
        annual_total=annual_total,
        monthly_total=monthly_total,
        annual_months=annual_months,
        category_summary=category_summary
    )


@app.route("/export/excel")
@login_required
def export_excel():
    subscriptions = get_user_subscriptions(session["user_id"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Suscripciones"

    ws.append([
        "Nombre",
        "Categoría",
        "Precio",
        "Ciclo",
        "Día renovación",
        "Estado",
        "Coste mensual estimado",
        "Coste anual estimado"
    ])

    for sub in subscriptions:
        price = float(sub["price"])

        if sub["billing_cycle"] == "monthly":
            monthly_cost = price
            annual_cost = price * 12
            cycle = "Mensual"
        else:
            monthly_cost = price / 12
            annual_cost = price
            cycle = "Anual"

        ws.append([
            sub["name"],
            sub["category"],
            price,
            cycle,
            sub["renewal_day"],
            "Activa" if sub["is_active"] else "Inactiva",
            round(monthly_cost, 2),
            round(annual_cost, 2)
        ])

    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name="subsy_suscripciones.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/export/pdf")
@login_required
def export_pdf():
    subscriptions = get_user_subscriptions(session["user_id"])
    monthly_total = calculate_monthly_total(subscriptions)
    annual_total = calculate_annual_total(subscriptions)

    file_stream = BytesIO()
    pdf = canvas.Canvas(file_stream, pagesize=A4)
    width, height = A4

    y = height - 2 * cm

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(2 * cm, y, "Subsy - Informe de suscripciones")

    y -= 1 * cm

    pdf.setFont("Helvetica", 11)
    pdf.drawString(2 * cm, y, f"Usuario: {session.get('username')}")
    y -= 0.6 * cm
    pdf.drawString(2 * cm, y, f"Total mensual estimado: {monthly_total} EUR")
    y -= 0.6 * cm
    pdf.drawString(2 * cm, y, f"Total anual estimado: {annual_total} EUR")

    y -= 1 * cm

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(2 * cm, y, "Suscripciones")

    y -= 0.7 * cm

    pdf.setFont("Helvetica", 9)

    for sub in subscriptions:
        if y < 2 * cm:
            pdf.showPage()
            y = height - 2 * cm
            pdf.setFont("Helvetica", 9)

        estado = "Activa" if sub["is_active"] else "Inactiva"
        ciclo = "Mensual" if sub["billing_cycle"] == "monthly" else "Anual"

        text = f"{sub['name']} | {sub['category']} | {sub['price']} EUR | {ciclo} | Dia {sub['renewal_day']} | {estado}"
        pdf.drawString(2 * cm, y, text[:110])
        y -= 0.5 * cm

    pdf.save()
    file_stream.seek(0)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name="subsy_informe.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)