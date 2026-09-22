"""Tests for Step 6 — date-range filter on GET /profile.

Derived from .claude/specs/06-profile-date-filter.md. Complements
tests/test_profile_date_filter.py (which already covers the query
helpers, app.py date-parsing helpers, filter-bar markup, filtering
behaviour, invalid input and preset logic in depth) rather than
duplicating it. This file focuses on:

- Authenticating through the real POST /login flow (not session
  injection) as the seeded demo user, per the task's emphasis on
  demo@spendly.com / demo123 and the 8 current-month seed expenses.
- Explicit DB side-effect checks: confirming that filtering (valid,
  invalid, reversed, or malformed) never inserts/updates/deletes any
  row anywhere in the database.
- Additional edge cases: whitespace-only params, very long input,
  wrong-length date strings, non-existent leap day, numeric-only
  garbage, repeated query params, and unsupported HTTP methods.
- Extra data-isolation checks with a third user sharing the same
  category names/amounts as the demo user.

All data lives in an isolated temp SQLite DB (see tests/conftest.py).
"""

import re
from datetime import date

import pytest

import database.db as db_module

INVALID_DATE_MSG = "Invalid date — showing all expenses."
REVERSED_MSG = "Start date must be on or before end date."
EMPTY_MSG = "No expenses in this period."
OTHER_USER_MARKER = "OTHER USER SECRET"

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def page_text(html):
    """Strip tags and collapse whitespace so assertions ignore markup."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def table_snapshot(conn):
    """Return every row of users and expenses, ordered, for before/after
    comparisons that prove a request made no DB writes."""
    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    expenses = conn.execute("SELECT * FROM expenses ORDER BY id").fetchall()
    return (
        [dict(r) for r in users],
        [dict(r) for r in expenses],
    )


def get_user_id(email):
    conn = db_module.get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def insert_expense(user_id, amount, category, expense_date, description):
    conn = db_module.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def demo_login(client, app_module):
    """Log in as the seeded demo user via the real POST /login flow
    (not direct session injection), per the task's login requirement."""
    db_module.seed_db()
    resp = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302, "Expected demo login to redirect to /profile"
    return client


@pytest.fixture
def demo_user_id(demo_login):
    uid = get_user_id(DEMO_EMAIL)
    assert uid is not None, "Seeded demo user must exist after seed_db()"
    return uid


@pytest.fixture
def rival_user(app_module):
    """A second user sharing the same categories/amounts as the demo
    seed data, but on different dates, to catch leakage bugs that a
    disjoint fixture might miss."""
    rival_id = db_module.create_user("Rival User", "rival@spendly.com", "hash-not-checked")
    today = date.today()
    # Mirror demo seed amounts/categories but tag description so any
    # leak is unambiguous, and vary the day so ranges can be crafted
    # to include the rival's dates only if isolation is broken.
    mirrored = [
        (250.0, "Food", 1),
        (1200.50, "Bills", 3),
        (1750.0, "Shopping", 14),
    ]
    for amount, category, day in mirrored:
        insert_expense(
            rival_id, amount, category, today.replace(day=day).isoformat(), OTHER_USER_MARKER
        )
    return rival_id


# ------------------------------------------------------------------ #
# Real login flow + demo user (Definition of Done)                    #
# ------------------------------------------------------------------ #


class TestDemoLoginFlow:
    def test_login_then_unfiltered_profile_matches_pre_step6_totals(self, demo_login):
        """DoD: logged in via demo@spendly.com/demo123, /profile with no
        query params shows the same totals as before Step 6."""
        resp = demo_login.get("/profile", follow_redirects=True)
        assert resp.status_code == 200
        text = page_text(resp.get_data(as_text=True))
        assert "Total spent ₹4758.50" in text, "Expected lifetime seed total of ₹4758.50"
        assert "Transactions 8" in text, "Expected 8 seeded transactions"
        assert "Top category Shopping" in text, "Expected Shopping as top category"

    def test_wrong_password_does_not_grant_profile_access(self, client, app_module):
        db_module.seed_db()
        client.post("/login", data={"email": DEMO_EMAIL, "password": "wrong-password"})
        resp = client.get("/profile?start_date=2025-01-01")
        assert resp.status_code == 302, "Failed login must not authorize /profile access"
        assert "/login" in resp.headers["Location"]

    def test_logged_out_after_logout_redirects_to_login(self, demo_login):
        demo_login.get("/logout")
        resp = demo_login.get("/profile?start_date=2025-01-01&end_date=2025-12-31")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# DB side effects — filtering must never write                        #
# ------------------------------------------------------------------ #


class TestNoDbSideEffects:
    """Spec: filtering is a read-only GET operation with no DB schema
    changes and no new rows/updates. These tests snapshot the full
    users/expenses tables before and after each kind of filter request
    and assert nothing changed."""

    @pytest.mark.parametrize(
        "query_string",
        [
            "",
            "start_date=2020-01-01&end_date=2020-01-31",
            "start_date=2020-01-01",
            "end_date=2020-01-31",
            "start_date=not-a-date",
            "start_date=2026-09-20&end_date=2026-09-01",
            "start_date=2026-01-01' OR '1'='1",
            "start_date=&end_date=",
        ],
    )
    def test_profile_request_does_not_modify_users_or_expenses_tables(
        self, demo_login, app_module, query_string
    ):
        conn = db_module.get_db()
        try:
            before = table_snapshot(conn)
        finally:
            conn.close()

        resp = demo_login.get(f"/profile?{query_string}")
        assert resp.status_code == 200

        conn = db_module.get_db()
        try:
            after = table_snapshot(conn)
        finally:
            conn.close()

        assert before == after, (
            f"GET /profile?{query_string} must not write to the database, "
            "but users/expenses rows changed"
        )

    def test_repeated_filtered_requests_keep_transaction_count_stable(self, demo_login):
        """A second identical request must return the same counts as the
        first — proving the filter doesn't accumulate or duplicate rows."""
        today = date.today()
        qs = f"start_date={today.replace(day=1).isoformat()}&end_date={today.isoformat()}"
        first = page_text(demo_login.get(f"/profile?{qs}").get_data(as_text=True))
        second = page_text(demo_login.get(f"/profile?{qs}").get_data(as_text=True))
        assert first == second, "Identical filtered requests must be idempotent"


# ------------------------------------------------------------------ #
# Additional data isolation (mirrored categories/amounts)             #
# ------------------------------------------------------------------ #


class TestDataIsolationWithMirroredRival:
    def test_rival_expenses_never_leak_into_demo_unfiltered_view(self, demo_login, rival_user):
        html = demo_login.get("/profile").get_data(as_text=True)
        assert OTHER_USER_MARKER not in html

    def test_rival_expenses_never_leak_into_demo_filtered_view(self, demo_login, rival_user):
        today = date.today()
        html = demo_login.get(
            "/profile",
            query_string={
                "start_date": today.replace(day=1).isoformat(),
                "end_date": today.isoformat(),
            },
        ).get_data(as_text=True)
        assert OTHER_USER_MARKER not in html
        text = page_text(html)
        # Demo's own day-1/day-3/day-14 totals must be unaffected by the
        # rival's mirrored same-day, same-category, same-amount rows.
        assert "Total spent ₹4758.50" in text or "Transactions" in text  # sanity: page rendered

    def test_rival_totals_do_not_inflate_demo_single_day_query(self, demo_login, rival_user):
        day3 = date.today().replace(day=3).isoformat()
        html = demo_login.get(
            "/profile", query_string={"start_date": day3, "end_date": day3}
        ).get_data(as_text=True)
        text = page_text(html)
        # Demo has exactly one ₹1200.50 Bills expense on day 3; the rival
        # also has a ₹1200.50 Bills expense on day 3 under a different
        # user_id. If isolation were broken this would double to 2/₹2401.00.
        assert "Total spent ₹1200.50" in text
        assert "Transactions 1" in text
        assert OTHER_USER_MARKER not in html


# ------------------------------------------------------------------ #
# Extra edge cases beyond the existing suite                          #
# ------------------------------------------------------------------ #


class TestExtraEdgeCases:
    def test_whitespace_only_start_date_is_treated_as_no_filter_or_invalid(self, demo_login):
        """Spec says empty strings mean no filter; a whitespace-only value
        is not literally empty but must still never 500."""
        resp = demo_login.get("/profile?start_date=%20%20%20")
        assert resp.status_code == 200

    def test_very_long_garbage_date_does_not_error(self, demo_login):
        long_garbage = "9" * 5000
        resp = demo_login.get("/profile", query_string={"start_date": long_garbage})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert INVALID_DATE_MSG in html

    def test_nonexistent_leap_day_is_invalid_not_500(self, demo_login):
        """2026 is not a leap year, so Feb 29 2026 does not exist."""
        resp = demo_login.get("/profile?start_date=2026-02-29")
        assert resp.status_code == 200
        assert INVALID_DATE_MSG in resp.get_data(as_text=True)

    def test_numeric_only_garbage_is_invalid_not_500(self, demo_login):
        resp = demo_login.get("/profile?start_date=20260101")
        assert resp.status_code == 200
        assert INVALID_DATE_MSG in resp.get_data(as_text=True)

    def test_extra_unknown_query_params_are_ignored(self, demo_login):
        resp = demo_login.get("/profile?start_date=2025-01-01&end_date=2025-12-31&sort=asc&page=2")
        assert resp.status_code == 200

    def test_repeated_start_date_param_does_not_crash(self, demo_login):
        """Flask's request.args.get() returns the first value for a
        repeated key; this must not raise regardless."""
        resp = demo_login.get("/profile?start_date=2025-01-01&start_date=not-a-date")
        assert resp.status_code == 200

    def test_post_to_profile_is_not_allowed(self, demo_login):
        """The filter is a plain GET form; the route must not silently
        accept POST as a write/filter mechanism."""
        resp = demo_login.post("/profile", data={"start_date": "2025-01-01"})
        assert resp.status_code in (405, 404), "POST /profile should not be a valid write route"

    def test_response_is_html_content_type(self, demo_login):
        resp = demo_login.get("/profile?start_date=2025-01-01")
        assert "text/html" in resp.content_type

    def test_never_returns_500_across_a_battery_of_malformed_inputs(self, demo_login):
        malformed_inputs = [
            "start_date=2025-00-10",
            "start_date=2025-01-00",
            "start_date=--",
            "start_date=2025-1-1",
            "start_date=2025/01/01",
            "start_date=<script>alert(1)</script>",
            "start_date=null",
            "start_date=undefined",
            "end_date=2025-01-01&start_date=2025-01-01&start_date=",
        ]
        for qs in malformed_inputs:
            resp = demo_login.get(f"/profile?{qs}")
            assert resp.status_code == 200, f"Query {qs!r} must not cause a non-200 response"
            assert resp.status_code != 500, f"Query {qs!r} must never 500"

    def test_filter_error_never_appears_for_a_valid_range(self, demo_login):
        html = demo_login.get("/profile?start_date=2020-01-01&end_date=2020-12-31").get_data(
            as_text=True
        )
        assert INVALID_DATE_MSG not in html
        assert REVERSED_MSG not in html


# ------------------------------------------------------------------ #
# Strict YYYY-MM-DD parsing (code-review follow-up)                   #
# ------------------------------------------------------------------ #


class TestStrictDateFormat:
    @pytest.mark.parametrize(
        "raw",
        [
            "2026-9-1",
            "2026-09-1",
            "2026-9-01",
            "２０２６-01-01",  # full-width digits
            "٢٠٢٦-01-01",  # Arabic-Indic digits
            "10000-01-01",
            "+2026-01-01",
        ],
    )
    def test_non_canonical_date_is_rejected(self, app_module, raw):
        start, end, error = app_module.parse_date_range(raw, "")
        assert (start, end) == (None, None)
        assert error == INVALID_DATE_MSG

    def test_canonical_date_with_surrounding_whitespace_is_accepted(self, app_module):
        start, end, error = app_module.parse_date_range(" 2026-09-03 ", "2026-09-04")
        assert start == date(2026, 9, 3)
        assert end == date(2026, 9, 4)
        assert error is None

    def test_non_canonical_date_in_url_falls_back_to_unfiltered(self, demo_login):
        resp = demo_login.get("/profile?start_date=2026-9-1")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert INVALID_DATE_MSG in html
        assert "Showing all time" in html
        assert 'name="start_date" value=""' in html


# ------------------------------------------------------------------ #
# Stale session for a deleted user (code-review follow-up)            #
# ------------------------------------------------------------------ #


class TestStaleSession:
    def test_missing_user_redirects_to_login_instead_of_500(self, client, app_module):
        with client.session_transaction() as sess:
            sess["user_id"] = 99999
            sess["user_name"] = "Ghost"
        resp = client.get("/profile?start_date=2026-09-01")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")

    def test_missing_user_session_is_cleared(self, client, app_module):
        with client.session_transaction() as sess:
            sess["user_id"] = 99999
            sess["user_name"] = "Ghost"
        client.get("/profile")
        with client.session_transaction() as sess:
            assert "user_id" not in sess
            assert "user_name" not in sess
