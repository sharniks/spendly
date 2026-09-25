import calendar
import csv
import io
import math
import os
import re
from datetime import date, datetime

from flask import Flask, Response, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_expense,
    create_user,
    delete_expense as delete_expense_row,
    get_expense_by_id,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)
from database.queries import (
    get_all_transactions,
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-before-production")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not name:
        return render_template("register.html", error="Name is required.")

    if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
        return render_template("register.html", error="Enter a valid email address.")

    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.")

    if get_user_by_email(email) is not None:
        return render_template("register.html", error="An account with that email already exists.")

    password_hash = generate_password_hash(password)
    create_user(name, email, password_hash)

    return redirect(url_for("login", registered=1))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        success = "Account created. Please sign in." if request.args.get("registered") else None
        return render_template("login.html", success=success)

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]

    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def format_member_since(created_at):
    dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%B %Y")


ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


def parse_iso_date(raw):
    if not ISO_DATE_PATTERN.fullmatch(raw):
        raise ValueError(f"not a YYYY-MM-DD date: {raw!r}")
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_date_range(raw_start, raw_end):
    raw_start = (raw_start or "").strip()
    raw_end = (raw_end or "").strip()

    try:
        start = parse_iso_date(raw_start) if raw_start else None
        end = parse_iso_date(raw_end) if raw_end else None
    except ValueError:
        return None, None, "Invalid date — showing all expenses."

    if start and end and start > end:
        return None, None, "Start date must be on or before end date."

    return start, end, None


def subtract_months(d, months):
    total = d.year * 12 + (d.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def get_presets(today):
    return {
        "this_month": (today.replace(day=1).isoformat(), today.isoformat()),
        "last_3_months": (subtract_months(today, 3).isoformat(), today.isoformat()),
    }


def format_display_date(d):
    return f"{d.day} {d.strftime('%b %Y')}"


def build_range_label(start, end):
    if start and end:
        return f"Showing {format_display_date(start)} – {format_display_date(end)}"
    if start:
        return f"Showing from {format_display_date(start)}"
    if end:
        return f"Showing up to {format_display_date(end)}"
    return "Showing all time"


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    start, end, filter_error = parse_date_range(
        request.args.get("start_date"), request.args.get("end_date")
    )
    start_iso = start.isoformat() if start else None
    end_iso = end.isoformat() if end else None

    presets = get_presets(date.today())
    active_preset = None
    if start_iso is None and end_iso is None:
        active_preset = "all"
    else:
        for key, preset_range in presets.items():
            if (start_iso, end_iso) == preset_range:
                active_preset = key
                break

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)
    if user_row is None:
        session.clear()
        return redirect(url_for("login"))
    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "member_since": format_member_since(user_row["created_at"]),
    }

    stats = get_summary_stats(user_id, start_iso, end_iso)
    transactions = get_recent_transactions(user_id, start_date=start_iso, end_date=end_iso)
    categories = get_category_breakdown(user_id, start_iso, end_iso)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        start_date=start_iso or "",
        end_date=end_iso or "",
        filter_error=filter_error,
        range_label=build_range_label(start, end),
        presets=presets,
        active_preset=active_preset,
    )


EXPENSE_CATEGORIES = [
    "Food",
    "Bills",
    "Transport",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

MAX_EXPENSE_AMOUNT = 10_000_000
MAX_DESCRIPTION_LENGTH = 255


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today_iso = date.today().isoformat()

    if request.method == "GET":
        return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, today=today_iso)

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()[:MAX_DESCRIPTION_LENGTH] or None

    def render_error(message):
        return render_template(
            "add_expense.html",
            categories=EXPENSE_CATEGORIES,
            today=today_iso,
            error=message,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description or "",
        )

    try:
        amount = float(amount_raw)
    except ValueError:
        return render_error("Enter a valid amount.")

    if not math.isfinite(amount) or amount <= 0 or amount > MAX_EXPENSE_AMOUNT:
        return render_error(f"Amount must be between 0 and {MAX_EXPENSE_AMOUNT:,}.")

    if category not in EXPENSE_CATEGORIES:
        return render_error("Select a valid category.")

    try:
        expense_date = parse_iso_date(date_raw) if date_raw else date.today()
    except ValueError:
        return render_error("Enter a valid date.")

    create_expense(session["user_id"], amount, category, expense_date.isoformat(), description)

    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id)
    if expense is None or expense["user_id"] != session["user_id"]:
        abort(404)

    if request.method == "GET":
        return render_template(
            "edit_expense.html",
            categories=EXPENSE_CATEGORIES,
            expense=expense,
        )

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()[:MAX_DESCRIPTION_LENGTH] or None

    def render_error(message):
        return render_template(
            "edit_expense.html",
            categories=EXPENSE_CATEGORIES,
            expense=expense,
            error=message,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description or "",
        )

    try:
        amount = float(amount_raw)
    except ValueError:
        return render_error("Enter a valid amount.")

    if not math.isfinite(amount) or amount <= 0 or amount > MAX_EXPENSE_AMOUNT:
        return render_error(f"Amount must be between 0 and {MAX_EXPENSE_AMOUNT:,}.")

    if category not in EXPENSE_CATEGORIES:
        return render_error("Select a valid category.")

    try:
        expense_date = parse_iso_date(date_raw) if date_raw else date.today()
    except ValueError:
        return render_error("Enter a valid date.")

    update_expense(id, amount, category, expense_date.isoformat(), description)

    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id)
    if expense is None or expense["user_id"] != session["user_id"]:
        abort(404)

    if request.method == "GET":
        return render_template("delete_expense.html", expense=expense)

    delete_expense_row(id)

    return redirect(url_for("profile"))


@app.route("/expenses/export")
def export_expenses():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    start, end, _filter_error = parse_date_range(
        request.args.get("start_date"), request.args.get("end_date")
    )
    start_iso = start.isoformat() if start else None
    end_iso = end.isoformat() if end else None

    transactions = get_all_transactions(session["user_id"], start_iso, end_iso)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Date", "Category", "Description", "Amount"])
    for tx in transactions:
        writer.writerow([tx["date"], tx["category"], tx["description"] or "", tx["amount"]])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
