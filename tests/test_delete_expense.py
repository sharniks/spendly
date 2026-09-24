"""Tests for Step 9 — GET/POST /expenses/<id>/delete.

Derived from .claude/specs/09-delete-expense.md (routes, ownership rules,
and Definition of Done) — not from reading app.py's delete_expense
implementation. All data lives in an isolated temp SQLite DB (see
tests/conftest.py); the `client` fixture is provided by pytest-flask from
the `app` fixture in conftest.py.
"""

import re

import pytest

import database.db as db_module

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


def delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def user_id(app_module):
    """A plain registered user, independent of seed data."""
    return db_module.create_user("Delete Expense Tester", "deleteexpense@test.com", "x-hash")


@pytest.fixture
def other_user_id(app_module):
    """A second, distinct registered user — used for ownership checks."""
    return db_module.create_user("Other User", "otheruser@test.com", "x-hash")


@pytest.fixture
def auth_client(client, user_id):
    """Client logged in as a fresh user with no existing expenses."""
    login_as(client, user_id, "Delete Expense Tester")
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
        resp = client.get(delete_url(expense_id))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_while_logged_out_redirects_to_login(self, client, expense_id):
        resp = client.post(delete_url(expense_id))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_while_logged_out_does_not_delete_row(self, client, expense_id):
        client.post(delete_url(expense_id))
        assert fetch_expense_by_id(expense_id) is not None

    def test_get_while_logged_out_for_nonexistent_id_still_redirects_to_login(self, client):
        """Auth guard should run before any existence check."""
        resp = client.get(delete_url(999999))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_get_while_logged_out_does_not_delete_row(self, client, expense_id):
        client.get(delete_url(expense_id))
        assert fetch_expense_by_id(expense_id) is not None


# ------------------------------------------------------------------ #
# Nonexistent expense -> 404                                          #
# ------------------------------------------------------------------ #


class TestNonexistentExpense:
    def test_get_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.get(delete_url(999999))
        assert resp.status_code == 404

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.post(delete_url(999999))
        assert resp.status_code == 404

    def test_post_nonexistent_expense_does_not_change_row_count(self, auth_client):
        before = count_all_expenses()
        auth_client.post(delete_url(999999))
        assert count_all_expenses() == before


# ------------------------------------------------------------------ #
# Ownership — another user's expense -> 404                           #
# ------------------------------------------------------------------ #


class TestOwnershipCheck:
    def test_get_another_users_expense_returns_404(self, auth_client, other_user_expense_id):
        resp = auth_client.get(delete_url(other_user_expense_id))
        assert resp.status_code == 404

    def test_post_another_users_expense_returns_404(self, auth_client, other_user_expense_id):
        resp = auth_client.post(delete_url(other_user_expense_id))
        assert resp.status_code == 404

    def test_post_another_users_expense_does_not_delete_row(
        self, auth_client, other_user_expense_id
    ):
        auth_client.post(delete_url(other_user_expense_id))
        assert fetch_expense_by_id(other_user_expense_id) is not None, (
            "Another user's expense must survive a failed delete attempt"
        )

    def test_404_does_not_reveal_existence_via_response_body(
        self, auth_client, other_user_expense_id
    ):
        """The 404 for 'exists but not yours' should look the same as a
        generic not-found; the spec says not to reveal existence."""
        resp = auth_client.get(delete_url(other_user_expense_id))
        html = resp.get_data(as_text=True)
        assert "Not yours" not in html
        assert "Bills" not in html


# ------------------------------------------------------------------ #
# GET on owned expense — confirmation page                            #
# ------------------------------------------------------------------ #


class TestConfirmationPage:
    def test_get_owned_expense_returns_200(self, auth_client, expense_id):
        resp = auth_client.get(delete_url(expense_id))
        assert resp.status_code == 200

    def test_confirmation_page_shows_date(self, auth_client, expense_id):
        html = auth_client.get(delete_url(expense_id)).get_data(as_text=True)
        assert "2025-05-01" in html, "Expected the expense date on the confirmation page"

    def test_confirmation_page_shows_category(self, auth_client, expense_id):
        html = auth_client.get(delete_url(expense_id)).get_data(as_text=True)
        assert "Food" in html, "Expected the expense category on the confirmation page"

    def test_confirmation_page_shows_description(self, auth_client, expense_id):
        html = auth_client.get(delete_url(expense_id)).get_data(as_text=True)
        assert "Original description" in html, (
            "Expected the expense description on the confirmation page"
        )

    def test_confirmation_page_shows_amount_in_inr(self, auth_client, expense_id):
        text = page_text(auth_client.get(delete_url(expense_id)).get_data(as_text=True))
        assert "₹100.00" in text, "Expected the amount formatted as INR (₹100.00)"

    def test_confirmation_page_has_delete_submit_form_posting_to_same_url(
        self, auth_client, expense_id
    ):
        html = auth_client.get(delete_url(expense_id)).get_data(as_text=True)
        form_match = re.search(r"<form\b[^>]*>", html)
        assert form_match, "Expected a <form> element on the confirmation page"
        form_tag = form_match.group(0)
        assert delete_url(expense_id) in form_tag, "Expected form action to target the delete URL"
        assert re.search(r'method=["\']?post', form_tag, re.I), (
            "Expected the confirmation form to submit via POST"
        )

    def test_confirmation_page_has_cancel_link_to_profile(self, auth_client, expense_id):
        html = auth_client.get(delete_url(expense_id)).get_data(as_text=True)
        assert re.search(r'href="[^"]*/profile"', html), (
            "Expected a Cancel link back to /profile"
        )

    def test_confirmation_page_does_not_delete_on_get(self, auth_client, expense_id):
        """Definition of done: a GET request never deletes the row."""
        auth_client.get(delete_url(expense_id))
        assert fetch_expense_by_id(expense_id) is not None

    def test_repeated_get_requests_never_delete_the_row(self, auth_client, expense_id):
        for _ in range(3):
            resp = auth_client.get(delete_url(expense_id))
            assert resp.status_code == 200
        assert fetch_expense_by_id(expense_id) is not None


# ------------------------------------------------------------------ #
# POST — happy path (actual deletion)                                 #
# ------------------------------------------------------------------ #


class TestDeletion:
    def test_post_redirects_to_profile(self, auth_client, expense_id):
        resp = auth_client.post(delete_url(expense_id), follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_post_deletes_the_row(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        assert fetch_expense_by_id(expense_id) is None

    def test_post_decrements_total_row_count(self, auth_client, expense_id):
        before = count_all_expenses()
        auth_client.post(delete_url(expense_id))
        assert count_all_expenses() == before - 1

    def test_post_does_not_affect_other_expenses_of_same_user(self, auth_client, user_id, expense_id):
        keep_id = db_module.create_expense(user_id, 20.00, "Bills", "2025-01-02", "Keep me")
        auth_client.post(delete_url(expense_id))
        assert fetch_expense_by_id(expense_id) is None
        assert fetch_expense_by_id(keep_id) is not None

    def test_post_does_not_affect_other_users_expenses(
        self, auth_client, expense_id, other_user_expense_id
    ):
        auth_client.post(delete_url(expense_id))
        assert fetch_expense_by_id(expense_id) is None
        assert fetch_expense_by_id(other_user_expense_id) is not None

    def test_getting_deleted_expense_again_returns_404(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        resp = auth_client.get(delete_url(expense_id))
        assert resp.status_code == 404

    def test_posting_deleted_expense_again_returns_404(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        resp = auth_client.post(delete_url(expense_id))
        assert resp.status_code == 404

    def test_demo_user_can_delete_their_own_expense_via_real_login(self, demo_client, app_module):
        demo_id = get_user_id(DEMO_EMAIL)
        own_expense = db_module.create_expense(
            demo_id, 12.00, "Food", "2025-01-01", "Demo expense to delete"
        )
        resp = demo_client.post(delete_url(own_expense), follow_redirects=False)
        assert resp.status_code == 302
        assert fetch_expense_by_id(own_expense) is None


# ------------------------------------------------------------------ #
# Definition of done — deleted expense disappears from /profile       #
# ------------------------------------------------------------------ #


class TestProfileReflectsDeletion:
    def test_deleted_expense_not_in_recent_transactions(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Original description" not in html

    def test_deleted_expense_excluded_from_summary_stats(self, auth_client, user_id, expense_id):
        db_module.create_expense(user_id, 50.00, "Bills", "2025-01-02", "Remaining expense")
        auth_client.post(delete_url(expense_id))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Total spent ₹50.00" in text
        assert "Transactions 1" in text

    def test_deleted_expense_excluded_from_category_breakdown(self, auth_client, user_id, expense_id):
        db_module.create_expense(user_id, 50.00, "Bills", "2025-01-02", "Remaining expense")
        auth_client.post(delete_url(expense_id))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Top category Bills" in text

    def test_deleting_only_expense_shows_empty_state(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        text = page_text(auth_client.get("/profile").get_data(as_text=True))
        assert "Total spent ₹0.00" in text
        assert "Transactions 0" in text

    def test_deleted_expense_edit_link_no_longer_on_profile(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert f"/expenses/{expense_id}/edit" not in html

    def test_deleted_expense_delete_link_no_longer_on_profile(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert delete_url(expense_id) not in html


# ------------------------------------------------------------------ #
# Definition of done — delete link on profile page                    #
# ------------------------------------------------------------------ #


class TestProfileDeleteLink:
    def test_profile_page_has_delete_link_for_transaction(self, auth_client, expense_id):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert re.search(rf'href="[^"]*{delete_url(expense_id)}"', html), (
            f"Expected a link to {delete_url(expense_id)} on the profile page"
        )

    def test_profile_delete_link_targets_correct_id_with_multiple_expenses(
        self, auth_client, user_id
    ):
        first_id = db_module.create_expense(user_id, 10.00, "Food", "2025-01-01", "First")
        second_id = db_module.create_expense(user_id, 20.00, "Bills", "2025-01-02", "Second")
        html = auth_client.get("/profile").get_data(as_text=True)
        assert re.search(rf'href="[^"]*{delete_url(first_id)}"', html), (
            "Expected a delete link for the first expense"
        )
        assert re.search(rf'href="[^"]*{delete_url(second_id)}"', html), (
            "Expected a delete link for the second expense"
        )

    def test_no_delete_link_for_nonexistent_expense_id(self, auth_client, expense_id):
        html = auth_client.get("/profile").get_data(as_text=True)
        bogus_url = delete_url(expense_id + 999999)
        assert bogus_url not in html

    def test_delete_link_distinct_from_edit_link(self, auth_client, expense_id):
        """Both an Edit and a Delete link should exist for the same row,
        pointing at different URLs."""
        html = auth_client.get("/profile").get_data(as_text=True)
        assert re.search(rf'href="[^"]*/expenses/{expense_id}/edit"', html), (
            "Expected an edit link alongside the delete link"
        )
        assert re.search(rf'href="[^"]*{delete_url(expense_id)}"', html), (
            "Expected a delete link alongside the edit link"
        )
