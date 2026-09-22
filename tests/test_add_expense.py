"""Tests for Step 7 — GET/POST /expenses/add.

Derived from .claude/specs/07-add-expense.md (routes, rules and Definition
of Done) — not from reading app.py's implementation. All data lives in an
isolated temp SQLite DB (see tests/conftest.py); the `client` fixture is
provided by pytest-flask from the `app` fixture in conftest.py.
"""

import re
from datetime import date

import pytest

import database.db as db_module

VALID_CATEGORIES = [
    "Food",
    "Bills",
    "Transport",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def page_text(html):
    """Strip tags and collapse whitespace so assertions ignore markup."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def get_user_id(email):
    conn = db_module.get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def fetch_expenses(user_id):
    conn = db_module.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_all_expenses():
    conn = db_module.get_db()
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
    finally:
        conn.close()


def login_as(client, user_id, name="Test User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def user_id(app_module):
    """A plain registered user, independent of seed data."""
    return db_module.create_user("Add Expense Tester", "addexpense@test.com", "x-hash")


@pytest.fixture
def auth_client(client, user_id):
    """Client logged in as a fresh user with no existing expenses."""
    login_as(client, user_id, "Add Expense Tester")
    return client


@pytest.fixture
def demo_client(client, app_module):
    """Client logged in as the seeded demo user via the real POST /login
    flow, per spec's mention of demo@spendly.com / demo123."""
    db_module.seed_db()
    resp = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302, "Expected demo login to redirect"
    return client


def valid_payload(**overrides):
    payload = {
        "amount": "42.50",
        "category": "Food",
        "date": "2025-06-15",
        "description": "Lunch",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #


class TestAuthGuard:
    def test_get_while_logged_out_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_while_logged_out_redirects_to_login(self, client):
        resp = client.post("/expenses/add", data=valid_payload())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_while_logged_out_does_not_insert_a_row(self, client):
        resp = client.post("/expenses/add", data=valid_payload())
        assert resp.status_code == 302
        assert count_all_expenses() == 0


# ------------------------------------------------------------------ #
# GET /expenses/add — form rendering                                  #
# ------------------------------------------------------------------ #


class TestFormRendering:
    def test_logged_in_get_returns_200(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200

    def test_form_has_amount_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert re.search(r'<input[^>]*name="amount"', html), "Expected an amount input"

    def test_form_has_category_dropdown_with_all_valid_options(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        select_match = re.search(r'<select[^>]*name="category".*?</select>', html, re.S)
        assert select_match, "Expected a category <select> field"
        select_html = select_match.group(0)
        for cat in VALID_CATEGORIES:
            assert cat in select_html, f"Expected category {cat!r} in dropdown"

    def test_form_has_date_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert re.search(r'name="date"', html), "Expected a date field"

    def test_form_has_description_field(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert re.search(r'name="description"', html), "Expected a description field"

    def test_form_posts_to_expenses_add(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        form = re.search(r"<form\b[^>]*>", html)
        assert form, "Expected a <form> element"
        assert "/expenses/add" in form.group(0)

    def test_no_error_banner_on_fresh_get(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        # No prior submission, so no validation error should be present.
        assert "Enter a valid amount" not in html
        assert "Amount must be greater than zero" not in html
        assert "Select a valid category" not in html
        assert "Enter a valid date" not in html


# ------------------------------------------------------------------ #
# POST /expenses/add — happy path                                     #
# ------------------------------------------------------------------ #


class TestValidSubmission:
    def test_valid_submission_redirects_to_profile(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_payload(), follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_submission_creates_exactly_one_row(self, auth_client, user_id):
        auth_client.post("/expenses/add", data=valid_payload())
        rows = fetch_expenses(user_id)
        assert len(rows) == 1

    def test_valid_submission_row_has_correct_user_id(self, auth_client, user_id):
        auth_client.post("/expenses/add", data=valid_payload())
        rows = fetch_expenses(user_id)
        assert rows[0]["user_id"] == user_id

    def test_valid_submission_row_has_correct_fields(self, auth_client, user_id):
        auth_client.post(
            "/expenses/add",
            data=valid_payload(
                amount="99.99", category="Bills", date="2025-07-04", description="Electricity bill"
            ),
        )
        row = fetch_expenses(user_id)[0]
        assert row["amount"] == pytest.approx(99.99)
        assert row["category"] == "Bills"
        assert row["date"] == "2025-07-04"
        assert row["description"] == "Electricity bill"

    def test_blank_date_defaults_to_today(self, auth_client, user_id):
        auth_client.post("/expenses/add", data=valid_payload(date=""))
        row = fetch_expenses(user_id)[0]
        assert row["date"] == date.today().isoformat()

    def test_new_expense_appears_in_profile_recent_transactions(self, auth_client):
        auth_client.post(
            "/expenses/add",
            data=valid_payload(
                amount="15.00",
                category="Entertainment",
                date="2025-08-01",
                description="Movie night",
            ),
        )
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Movie night" in html

    def test_new_expense_reflected_in_summary_stats(self, auth_client):
        auth_client.post(
            "/expenses/add",
            data=valid_payload(amount="123.45", category="Shopping", date="2025-08-01"),
        )
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Total spent ₹123.45" in text
        assert "Transactions 1" in text

    def test_new_expense_reflected_in_category_breakdown(self, auth_client):
        auth_client.post(
            "/expenses/add",
            data=valid_payload(amount="50.00", category="Health", date="2025-08-01"),
        )
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Top category Health" in text

    def test_second_expense_updates_totals_cumulatively(self, auth_client):
        auth_client.post("/expenses/add", data=valid_payload(amount="10.00", date="2025-01-01"))
        auth_client.post("/expenses/add", data=valid_payload(amount="20.00", date="2025-01-02"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Total spent ₹30.00" in text
        assert "Transactions 2" in text

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, auth_client, user_id, category):
        resp = auth_client.post("/expenses/add", data=valid_payload(category=category))
        assert resp.status_code == 302
        rows = fetch_expenses(user_id)
        assert rows[-1]["category"] == category

    def test_demo_user_can_add_an_expense_via_real_login(self, demo_client):
        demo_id = get_user_id(DEMO_EMAIL)
        before = len(fetch_expenses(demo_id))
        resp = demo_client.post(
            "/expenses/add",
            data=valid_payload(amount="77.00", category="Transport", date="2025-09-01"),
            follow_redirects=False,
        )
        assert resp.status_code == 302
        after = fetch_expenses(demo_id)
        assert len(after) == before + 1


# ------------------------------------------------------------------ #
# POST /expenses/add — invalid amount                                 #
# ------------------------------------------------------------------ #


class TestInvalidAmount:
    def test_missing_amount_rerenders_form_with_error(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data=valid_payload(amount=""))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert re.search(r"error|invalid|required", html, re.I), (
            "Expected a validation error message for missing amount"
        )
        assert fetch_expenses(user_id) == []

    def test_zero_amount_rerenders_form_with_error(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data=valid_payload(amount="0"))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_negative_amount_rerenders_form_with_error(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data=valid_payload(amount="-5"))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_non_numeric_amount_rerenders_form_with_error(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data=valid_payload(amount="not-a-number"))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    @pytest.mark.parametrize("bad_amount", ["", "0", "-1", "-0.01", "abc", "NaN", "1e"])
    def test_no_row_inserted_for_any_invalid_amount(self, auth_client, user_id, bad_amount):
        auth_client.post("/expenses/add", data=valid_payload(amount=bad_amount))
        assert fetch_expenses(user_id) == []

    def test_invalid_amount_response_is_200_not_redirect(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_payload(amount="-5"))
        assert resp.status_code == 200
        assert resp.status_code != 302

    def test_invalid_amount_does_not_affect_profile_stats(self, auth_client):
        auth_client.post("/expenses/add", data=valid_payload(amount="0"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Transactions 0" in text


# ------------------------------------------------------------------ #
# POST /expenses/add — invalid category                               #
# ------------------------------------------------------------------ #


class TestInvalidCategory:
    def test_empty_category_rerenders_form_with_error(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data=valid_payload(category=""))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_category_not_in_fixed_list_rerenders_form_with_error(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data=valid_payload(category="Groceries"))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_category_case_mismatch_is_rejected(self, auth_client, user_id):
        """The fixed set is case-sensitive; 'food' is not 'Food'."""
        resp = auth_client.post("/expenses/add", data=valid_payload(category="food"))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_invalid_category_does_not_redirect(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_payload(category="Invalid"))
        assert resp.status_code == 200

    def test_invalid_category_does_not_affect_profile_stats(self, auth_client):
        auth_client.post("/expenses/add", data=valid_payload(category=""))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Transactions 0" in text


# ------------------------------------------------------------------ #
# POST /expenses/add — invalid date                                   #
# ------------------------------------------------------------------ #


class TestInvalidDate:
    @pytest.mark.parametrize(
        "bad_date",
        [
            "not-a-date",
            "2025-13-01",
            "2025-02-30",
            "01/02/2025",
            "2025/01/01",
            "2025-1-1",
        ],
    )
    def test_invalid_date_format_rerenders_form_with_error(self, auth_client, user_id, bad_date):
        resp = auth_client.post("/expenses/add", data=valid_payload(date=bad_date))
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_invalid_date_does_not_redirect(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_payload(date="garbage"))
        assert resp.status_code == 200

    def test_invalid_date_does_not_affect_profile_stats(self, auth_client):
        auth_client.post("/expenses/add", data=valid_payload(date="garbage"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Transactions 0" in text

    def test_valid_explicit_date_is_stored_as_given(self, auth_client, user_id):
        auth_client.post("/expenses/add", data=valid_payload(date="2024-12-25"))
        row = fetch_expenses(user_id)[0]
        assert row["date"] == "2024-12-25"


# ------------------------------------------------------------------ #
# Combined / multiple invalid fields                                  #
# ------------------------------------------------------------------ #


class TestMultipleInvalidFields:
    def test_all_fields_invalid_still_returns_200_without_insert(self, auth_client, user_id):
        resp = auth_client.post(
            "/expenses/add",
            data={"amount": "-1", "category": "", "date": "bad-date", "description": ""},
        )
        assert resp.status_code == 200
        assert fetch_expenses(user_id) == []

    def test_missing_form_fields_entirely_does_not_500(self, auth_client, user_id):
        resp = auth_client.post("/expenses/add", data={})
        assert resp.status_code == 200
        assert resp.status_code != 500
        assert fetch_expenses(user_id) == []


# ------------------------------------------------------------------ #
# Definition of done — link from profile page                         #
# ------------------------------------------------------------------ #


class TestProfileLink:
    def test_profile_page_has_link_to_add_expense(self, auth_client):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert re.search(r'href="[^"]*/expenses/add"', html), (
            "Expected a link to /expenses/add on the profile page"
        )
