"""Tests for Step 8 — GET/POST /expenses/<id>/edit.

Derived from .claude/specs/08-edit-expense.md (routes, ownership rules,
validation rules and Definition of Done) — not from reading app.py's
edit_expense implementation. All data lives in an isolated temp SQLite DB
(see tests/conftest.py); the `client` fixture is provided by pytest-flask
from the `app` fixture in conftest.py.
"""

import re

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


def fetch_expense_by_id(expense_id):
    conn = db_module.get_db()
    try:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        return dict(row) if row else None
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


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


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
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def user_id(app_module):
    """A plain registered user, independent of seed data."""
    return db_module.create_user("Edit Expense Tester", "editexpense@test.com", "x-hash")


@pytest.fixture
def other_user_id(app_module):
    """A second, distinct registered user — used for ownership checks."""
    return db_module.create_user("Other User", "otheruser@test.com", "x-hash")


@pytest.fixture
def auth_client(client, user_id):
    """Client logged in as a fresh user with no existing expenses."""
    login_as(client, user_id, "Edit Expense Tester")
    return client


@pytest.fixture
def expense_id(app_module, user_id):
    """An existing expense owned by `user_id`, created directly via the DB
    helper (not via the add-expense route) so these tests are independent
    of Step 7's behavior."""
    return db_module.create_expense(
        user_id,
        amount=100.00,
        category="Food",
        expense_date="2025-05-01",
        description="Original description",
    )


@pytest.fixture
def other_user_expense_id(app_module, other_user_id):
    """An expense owned by a different user than `auth_client`."""
    return db_module.create_expense(
        other_user_id,
        amount=55.00,
        category="Bills",
        expense_date="2025-05-02",
        description="Not yours",
    )


@pytest.fixture
def demo_client(client, app_module):
    """Client logged in as the seeded demo user via the real POST /login
    flow."""
    db_module.seed_db()
    resp = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302, "Expected demo login to redirect"
    return client


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #


class TestAuthGuard:
    def test_get_while_logged_out_redirects_to_login(self, client, expense_id):
        resp = client.get(edit_url(expense_id))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_while_logged_out_redirects_to_login(self, client, expense_id):
        resp = client.post(edit_url(expense_id), data=valid_payload())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_while_logged_out_does_not_modify_row(self, client, expense_id):
        original = fetch_expense_by_id(expense_id)
        client.post(edit_url(expense_id), data=valid_payload(amount="999.00"))
        after = fetch_expense_by_id(expense_id)
        assert after == original

    def test_get_while_logged_out_for_nonexistent_id_still_redirects_to_login(self, client):
        """Auth guard should run before any existence check."""
        resp = client.get(edit_url(999999))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# Nonexistent expense -> 404                                          #
# ------------------------------------------------------------------ #


class TestNonexistentExpense:
    def test_get_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.get(edit_url(999999))
        assert resp.status_code == 404

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.post(edit_url(999999), data=valid_payload())
        assert resp.status_code == 404

    def test_post_nonexistent_expense_does_not_insert_a_row(self, auth_client):
        before = count_all_expenses()
        auth_client.post(edit_url(999999), data=valid_payload())
        assert count_all_expenses() == before


# ------------------------------------------------------------------ #
# Ownership — another user's expense -> 404                           #
# ------------------------------------------------------------------ #


class TestOwnershipCheck:
    def test_get_another_users_expense_returns_404(self, auth_client, other_user_expense_id):
        resp = auth_client.get(edit_url(other_user_expense_id))
        assert resp.status_code == 404

    def test_post_another_users_expense_returns_404(self, auth_client, other_user_expense_id):
        resp = auth_client.post(edit_url(other_user_expense_id), data=valid_payload())
        assert resp.status_code == 404

    def test_post_another_users_expense_does_not_modify_row(
        self, auth_client, other_user_expense_id
    ):
        original = fetch_expense_by_id(other_user_expense_id)
        auth_client.post(
            edit_url(other_user_expense_id), data=valid_payload(amount="1.00", description="Hax")
        )
        after = fetch_expense_by_id(other_user_expense_id)
        assert after == original

    def test_404_does_not_reveal_existence_via_response_body(
        self, auth_client, other_user_expense_id
    ):
        """The 404 for 'exists but not yours' should look the same as a
        generic not-found; the spec says not to reveal existence."""
        resp = auth_client.get(edit_url(other_user_expense_id))
        html = resp.get_data(as_text=True)
        assert "Not yours" not in html
        assert "Bills" not in html


# ------------------------------------------------------------------ #
# GET on owned expense — form pre-fill                                #
# ------------------------------------------------------------------ #


class TestFormPrefill:
    def test_get_owned_expense_returns_200(self, auth_client, expense_id):
        resp = auth_client.get(edit_url(expense_id))
        assert resp.status_code == 200

    def test_form_prefilled_with_current_amount(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert re.search(r'name="amount"[^>]*value="100(\.0+)?"', html), (
            "Expected amount input pre-filled with 100.00"
        )

    def test_form_prefilled_with_current_category_selected(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        select_match = re.search(r'<select[^>]*name="category".*?</select>', html, re.S)
        assert select_match, "Expected a category <select> field"
        select_html = select_match.group(0)
        option_match = re.search(
            r'<option[^>]*value="Food"[^>]*selected', select_html
        ) or re.search(r'<option[^>]*selected[^>]*value="Food"', select_html)
        assert option_match, "Expected 'Food' option to be pre-selected"

    def test_form_prefilled_with_current_date(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert re.search(r'name="date"[^>]*value="2025-05-01"', html), (
            "Expected date input pre-filled with 2025-05-01"
        )

    def test_form_prefilled_with_current_description(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert "Original description" in html

    def test_form_action_points_to_same_expense_edit_url(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        form = re.search(r"<form\b[^>]*>", html)
        assert form, "Expected a <form> element"
        assert edit_url(expense_id) in form.group(0)

    def test_form_has_all_valid_category_options(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        select_match = re.search(r'<select[^>]*name="category".*?</select>', html, re.S)
        assert select_match
        select_html = select_match.group(0)
        for cat in VALID_CATEGORIES:
            assert cat in select_html, f"Expected category {cat!r} in dropdown"

    def test_no_error_banner_on_fresh_get(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert "Enter a valid amount" not in html
        assert "Amount must be greater than zero" not in html
        assert "Select a valid category" not in html
        assert "Enter a valid date" not in html


# ------------------------------------------------------------------ #
# POST — happy path                                                   #
# ------------------------------------------------------------------ #


class TestValidSubmission:
    def test_valid_submission_redirects_to_profile(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(), follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_submission_updates_row_fields(self, auth_client, expense_id):
        auth_client.post(
            edit_url(expense_id),
            data=valid_payload(
                amount="250.75",
                category="Bills",
                date="2025-07-04",
                description="Electricity bill",
            ),
        )
        row = fetch_expense_by_id(expense_id)
        assert row["amount"] == pytest.approx(250.75)
        assert row["category"] == "Bills"
        assert row["date"] == "2025-07-04"
        assert row["description"] == "Electricity bill"

    def test_valid_submission_does_not_change_id(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload())
        row = fetch_expense_by_id(expense_id)
        assert row["id"] == expense_id

    def test_valid_submission_does_not_change_user_id(self, auth_client, expense_id, user_id):
        auth_client.post(edit_url(expense_id), data=valid_payload())
        row = fetch_expense_by_id(expense_id)
        assert row["user_id"] == user_id

    def test_valid_submission_does_not_create_a_new_row(self, auth_client, expense_id, user_id):
        auth_client.post(edit_url(expense_id), data=valid_payload())
        assert len(fetch_expenses(user_id)) == 1

    def test_updated_description_appears_in_profile_recent_transactions(
        self, auth_client, expense_id
    ):
        auth_client.post(
            edit_url(expense_id),
            data=valid_payload(description="Updated movie night"),
        )
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Updated movie night" in html
        assert "Original description" not in html

    def test_updated_amount_reflected_in_summary_stats(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload(amount="321.00"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Total spent ₹321.00" in text
        assert "Transactions 1" in text

    def test_updated_category_reflected_in_category_breakdown(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload(category="Health"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Top category Health" in text

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, auth_client, expense_id, category):
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(category=category))
        assert resp.status_code == 302
        row = fetch_expense_by_id(expense_id)
        assert row["category"] == category

    def test_demo_user_can_edit_their_own_expense_via_real_login(self, demo_client, app_module):
        demo_id = get_user_id(DEMO_EMAIL)
        own_expense = db_module.create_expense(
            demo_id, 12.00, "Food", "2025-01-01", "Demo original"
        )
        resp = demo_client.post(
            edit_url(own_expense),
            data=valid_payload(amount="88.00", description="Demo updated"),
            follow_redirects=False,
        )
        assert resp.status_code == 302
        row = fetch_expense_by_id(own_expense)
        assert row["amount"] == pytest.approx(88.00)
        assert row["description"] == "Demo updated"


# ------------------------------------------------------------------ #
# POST — invalid amount                                               #
# ------------------------------------------------------------------ #


class TestInvalidAmount:
    def test_missing_amount_rerenders_form_with_error(self, auth_client, expense_id):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(amount=""))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert re.search(r"error|invalid|required", html, re.I), (
            "Expected a validation error message for missing amount"
        )
        assert fetch_expense_by_id(expense_id) == original

    def test_zero_amount_rerenders_form_with_error_and_no_mutation(self, auth_client, expense_id):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(amount="0"))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_negative_amount_rerenders_form_with_error_and_no_mutation(
        self, auth_client, expense_id
    ):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(amount="-5"))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_non_numeric_amount_rerenders_form_with_error_and_no_mutation(
        self, auth_client, expense_id
    ):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(amount="not-a-number"))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    @pytest.mark.parametrize("bad_amount", ["", "0", "-1", "-0.01", "abc", "NaN", "1e"])
    def test_row_unchanged_for_any_invalid_amount(self, auth_client, expense_id, bad_amount):
        original = fetch_expense_by_id(expense_id)
        auth_client.post(edit_url(expense_id), data=valid_payload(amount=bad_amount))
        assert fetch_expense_by_id(expense_id) == original

    def test_invalid_amount_response_is_200_not_redirect(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(amount="-5"))
        assert resp.status_code == 200
        assert resp.status_code != 302

    def test_invalid_amount_does_not_change_profile_stats(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload(amount="0"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        # The original expense (100.00) should still be the one reflected.
        assert "Total spent ₹100.00" in text
        assert "Transactions 1" in text


# ------------------------------------------------------------------ #
# POST — invalid category                                             #
# ------------------------------------------------------------------ #


class TestInvalidCategory:
    def test_empty_category_rerenders_form_with_error_and_no_mutation(
        self, auth_client, expense_id
    ):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(category=""))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_category_not_in_fixed_list_rerenders_form_with_error_and_no_mutation(
        self, auth_client, expense_id
    ):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(category="Groceries"))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_category_case_mismatch_is_rejected(self, auth_client, expense_id):
        """The fixed set is case-sensitive; 'food' is not 'Food'."""
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(category="food"))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_invalid_category_does_not_redirect(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(category="Invalid"))
        assert resp.status_code == 200

    def test_invalid_category_does_not_change_profile_stats(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload(category=""))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Top category Food" in text


# ------------------------------------------------------------------ #
# POST — invalid date                                                 #
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
    def test_invalid_date_format_rerenders_form_with_error_and_no_mutation(
        self, auth_client, expense_id, bad_date
    ):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(date=bad_date))
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_invalid_date_does_not_redirect(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=valid_payload(date="garbage"))
        assert resp.status_code == 200

    def test_invalid_date_does_not_change_profile_stats(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload(date="garbage"))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "2025-05-01" in page_text(
            auth_client.get("/profile").get_data(as_text=True)
        ) or "May" in text or "05" in text

    def test_valid_explicit_date_is_stored_as_given(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=valid_payload(date="2024-12-25"))
        row = fetch_expense_by_id(expense_id)
        assert row["date"] == "2024-12-25"


# ------------------------------------------------------------------ #
# Combined / multiple invalid fields                                  #
# ------------------------------------------------------------------ #


class TestMultipleInvalidFields:
    def test_all_fields_invalid_still_returns_200_without_mutation(self, auth_client, expense_id):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(
            edit_url(expense_id),
            data={"amount": "-1", "category": "", "date": "bad-date", "description": ""},
        )
        assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) == original

    def test_missing_form_fields_entirely_does_not_500(self, auth_client, expense_id):
        original = fetch_expense_by_id(expense_id)
        resp = auth_client.post(edit_url(expense_id), data={})
        assert resp.status_code == 200
        assert resp.status_code != 500
        assert fetch_expense_by_id(expense_id) == original


# ------------------------------------------------------------------ #
# Definition of done — edit link on profile page                      #
# ------------------------------------------------------------------ #


class TestProfileEditLink:
    def test_profile_page_has_edit_link_for_transaction(self, auth_client, expense_id):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert re.search(rf'href="[^"]*{edit_url(expense_id)}"', html), (
            f"Expected a link to {edit_url(expense_id)} on the profile page"
        )

    def test_profile_edit_link_targets_correct_id_with_multiple_expenses(
        self, auth_client, user_id
    ):
        first_id = db_module.create_expense(user_id, 10.00, "Food", "2025-01-01", "First")
        second_id = db_module.create_expense(user_id, 20.00, "Bills", "2025-01-02", "Second")
        html = auth_client.get("/profile").get_data(as_text=True)
        assert re.search(rf'href="[^"]*{edit_url(first_id)}"', html), (
            "Expected an edit link for the first expense"
        )
        assert re.search(rf'href="[^"]*{edit_url(second_id)}"', html), (
            "Expected an edit link for the second expense"
        )

    def test_no_edit_link_for_nonexistent_expense_id(self, auth_client, expense_id):
        html = auth_client.get("/profile").get_data(as_text=True)
        bogus_url = edit_url(expense_id + 999999)
        assert bogus_url not in html
