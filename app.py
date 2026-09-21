from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import create_user, get_user_by_email, init_db, seed_db

app = Flask(__name__)

# Dev-only secret key — replace with a value loaded from an environment
# variable before deploying to production.
app.secret_key = "dev-secret-key-change-before-production"

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


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": session.get("user_name", "Demo User"),
        "email": "demo@spendly.com",
        "member_since": "January 2025",
    }

    stats = {
        "total_spent": 4758.50,
        "transaction_count": 8,
        "top_category": "Shopping",
    }

    transactions = [
        {
            "date": "2026-09-21",
            "description": "Lunch with colleagues",
            "category": "Food",
            "amount": 120.00,
        },
        {
            "date": "2026-09-14",
            "description": "New shoes",
            "category": "Shopping",
            "amount": 1750.00,
        },
        {
            "date": "2026-09-10",
            "description": "Movie tickets",
            "category": "Entertainment",
            "amount": 599.00,
        },
        {
            "date": "2026-09-07",
            "description": "Pharmacy purchase",
            "category": "Health",
            "amount": 450.00,
        },
        {
            "date": "2026-09-05",
            "description": "Auto rickshaw fare",
            "category": "Transport",
            "amount": 89.00,
        },
    ]

    categories = [
        {"name": "Shopping", "total": 1750.00, "percent": 37},
        {"name": "Bills", "total": 1200.50, "percent": 25},
        {"name": "Entertainment", "total": 599.00, "percent": 13},
        {"name": "Health", "total": 450.00, "percent": 9},
        {"name": "Food", "total": 370.00, "percent": 8},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
