"""Tests for Step 6 — date-range filter on GET /profile.

Derived from .claude/specs/06-profile-date-filter.md (routes, rules and
Definition of Done). All data lives in an isolated temp SQLite DB
(see conftest.py).
"""

import calendar
import re
from datetime import date, timedelta

import pytest

import database.db as db_module
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

INVALID_DATE_MSG = "Invalid date — showing all expenses."
REVERSED_MSG = "Start date must be on or before end date."
EMPTY_MSG = "No expenses in this period."
OTHER_USER_MARKER = "OTHER USER SECRET"


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


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


def get_user_id(email):
    conn = db_module.get_db()
    try:
        return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    finally:
        conn.close()


def login_as(client, user_id, name="Test User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name


def page_text(html):
    """Strip tags and collapse whitespace so assertions ignore markup."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def input_value(html, name):
    match = re.search(r'<input[^>]*name="%s"[^>]*>' % re.escape(name), html)
    assert match, f"input {name!r} not found"
    value = re.search(r'value="([^"]*)"', match.group(0))
    return value.group(1) if value else ""


def preset_anchor(html, label):
    match = re.search(r"<a\b[^>]*>\s*%s\s*</a>" % re.escape(label), html)
    assert match, f"preset link {label!r} not found"
    return match.group(0)


def is_active(anchor):
    cls = re.search(r'class="([^"]*)"', anchor)
    return bool(cls) and "is-active" in cls.group(1).split()


def three_months_before(d):
    """Spec: same day 3 calendar months earlier, clamped to a valid day."""
    total = d.year * 12 + (d.month - 1) - 3
    year, month0 = divmod(total, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def users(app):
    """A main user with fixed 2025 expenses and a second user with
    expenses on the same dates (for data-isolation checks)."""
    main_id = db_module.create_user("Filter Tester", "filter@test.com", "x-hash")
    other_id = db_module.create_user("Other Person", "other@test.com", "x-hash")

    insert_expense(main_id, 100.0, "Food", "2025-01-10", "Jan groceries")
    insert_expense(main_id, 200.0, "Bills", "2025-02-15", "Feb electricity")
    insert_expense(main_id, 300.0, "Shopping", "2025-03-20", "Mar jacket")

    for d in ("2025-01-10", "2025-02-15", "2025-03-20"):
        insert_expense(other_id, 5000.0, "Travel", d, OTHER_USER_MARKER)

    return {"main": main_id, "other": other_id}


@pytest.fixture
def main_client(client, users):
    login_as(client, users["main"], "Filter Tester")
    return client


@pytest.fixture
def demo_client(client, app):
    """Logged in as the seeded demo user (seed data relative to today)."""
    db_module.seed_db()
    demo_id = get_user_id("demo@spendly.com")
    other_id = db_module.create_user("Other Person", "other@test.com", "x-hash")
    today = date.today()
    for day in (1, 3, 14):
        insert_expense(
            other_id, 5000.0, "Travel", today.replace(day=day).isoformat(), OTHER_USER_MARKER
        )
    login_as(client, demo_id, "Demo User")
    return client


@pytest.fixture
def preset_client(client, app):
    """User whose expenses straddle the preset boundaries (relative to today)."""
    uid = db_module.create_user("Preset Tester", "preset@test.com", "x-hash")
    today = date.today()
    first = today.replace(day=1)
    three_ago = three_months_before(today)
    insert_expense(uid, 10.0, "Food", today.isoformat(), "today")
    if first != today:
        insert_expense(uid, 20.0, "Bills", first.isoformat(), "first of month")
    else:
        insert_expense(uid, 20.0, "Bills", today.isoformat(), "first of month")
    insert_expense(uid, 40.0, "Health", (first - timedelta(days=1)).isoformat(), "last month end")
    insert_expense(uid, 80.0, "Transport", three_ago.isoformat(), "three months ago")
    insert_expense(uid, 160.0, "Other", (three_ago - timedelta(days=1)).isoformat(), "too old")
    login_as(client, uid, "Preset Tester")
    return client


# ------------------------------------------------------------------ #
# Query helpers (database/queries.py)                                 #
# ------------------------------------------------------------------ #


class TestQueryHelpers:
    def test_summary_stats_unfiltered_with_only_user_id(self, users):
        stats = get_summary_stats(users["main"])
        assert stats["total_spent"] == pytest.approx(600.0)
        assert stats["transaction_count"] == 3
        assert stats["top_category"] == "Shopping"

    def test_recent_transactions_unfiltered_with_only_user_id(self, users):
        txs = get_recent_transactions(users["main"])
        assert len(txs) == 3
        assert {t["date"] for t in txs} == {"2025-01-10", "2025-02-15", "2025-03-20"}

    def test_category_breakdown_unfiltered_with_only_user_id(self, users):
        cats = get_category_breakdown(users["main"])
        assert {c["name"] for c in cats} == {"Food", "Bills", "Shopping"}
        assert sum(c["percent"] for c in cats) == 100

    def test_summary_stats_range_is_inclusive_on_both_ends(self, users):
        stats = get_summary_stats(users["main"], "2025-01-10", "2025-02-15")
        assert stats["total_spent"] == pytest.approx(300.0)
        assert stats["transaction_count"] == 2
        assert stats["top_category"] == "Bills"

    def test_recent_transactions_range_is_inclusive(self, users):
        txs = get_recent_transactions(users["main"], start_date="2025-02-15", end_date="2025-03-20")
        assert sorted(t["date"] for t in txs) == ["2025-02-15", "2025-03-20"]

    def test_category_breakdown_range(self, users):
        cats = get_category_breakdown(users["main"], "2025-02-01", "2025-02-28")
        assert len(cats) == 1
        assert cats[0]["name"] == "Bills"
        assert cats[0]["percent"] == 100

    def test_start_date_only_is_open_ended(self, users):
        stats = get_summary_stats(users["main"], start_date="2025-02-01")
        assert stats["transaction_count"] == 2
        assert stats["total_spent"] == pytest.approx(500.0)

    def test_end_date_only_is_open_ended(self, users):
        stats = get_summary_stats(users["main"], end_date="2025-02-15")
        assert stats["transaction_count"] == 2
        assert stats["total_spent"] == pytest.approx(300.0)

    def test_empty_range_returns_zero_state(self, users):
        stats = get_summary_stats(users["main"], "2024-01-01", "2024-12-31")
        assert stats["total_spent"] == 0
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—"
        assert (
            get_recent_transactions(users["main"], start_date="2024-01-01", end_date="2024-12-31")
            == []
        )
        assert get_category_breakdown(users["main"], "2024-01-01", "2024-12-31") == []

    def test_filters_never_include_other_users_expenses(self, users):
        stats = get_summary_stats(users["main"], "2025-01-01", "2025-12-31")
        assert stats["total_spent"] == pytest.approx(600.0)
        txs = get_recent_transactions(users["main"], start_date="2025-01-01", end_date="2025-12-31")
        assert all(t["description"] != OTHER_USER_MARKER for t in txs)
        cats = get_category_breakdown(users["main"], "2025-01-01", "2025-12-31")
        assert "Travel" not in {c["name"] for c in cats}


# ------------------------------------------------------------------ #
# Date helpers in app.py                                              #
# ------------------------------------------------------------------ #


class TestDateHelpers:
    @pytest.mark.parametrize(
        "raw_start, raw_end, expected",
        [
            (None, None, (None, None, None)),
            ("", "", (None, None, None)),
            ("2025-01-01", "2025-01-31", (date(2025, 1, 1), date(2025, 1, 31), None)),
            ("2025-01-01", None, (date(2025, 1, 1), None, None)),
            (None, "2025-01-31", (None, date(2025, 1, 31), None)),
            ("2025-05-05", "2025-05-05", (date(2025, 5, 5), date(2025, 5, 5), None)),
        ],
    )
    def test_parse_date_range_valid(self, app_module, raw_start, raw_end, expected):
        assert app_module.parse_date_range(raw_start, raw_end) == expected

    @pytest.mark.parametrize(
        "raw_start, raw_end",
        [
            ("not-a-date", None),
            (None, "garbage"),
            ("2025-02-30", None),
            ("2026-01-01' OR '1'='1", None),
            ("01/02/2025", None),
        ],
    )
    def test_parse_date_range_invalid(self, app_module, raw_start, raw_end):
        start, end, error = app_module.parse_date_range(raw_start, raw_end)
        assert (start, end) == (None, None)
        assert error == INVALID_DATE_MSG

    def test_parse_date_range_reversed(self, app_module):
        start, end, error = app_module.parse_date_range("2026-09-20", "2026-09-01")
        assert (start, end) == (None, None)
        assert error == REVERSED_MSG

    @pytest.mark.parametrize(
        "given, expected",
        [
            (date(2026, 9, 23), date(2026, 6, 23)),
            (date(2026, 5, 31), date(2026, 2, 28)),
            (date(2024, 5, 31), date(2024, 2, 29)),
            (date(2026, 1, 15), date(2025, 10, 15)),
            (date(2026, 3, 1), date(2025, 12, 1)),
        ],
    )
    def test_subtract_three_months_clamps(self, app_module, given, expected):
        assert app_module.subtract_months(given, 3) == expected

    def test_get_presets(self, app_module):
        presets = app_module.get_presets(date(2026, 9, 23))
        assert presets["this_month"] == ("2026-09-01", "2026-09-23")
        assert presets["last_3_months"] == ("2026-06-23", "2026-09-23")


# ------------------------------------------------------------------ #
# GET /profile — auth                                                 #
# ------------------------------------------------------------------ #


class TestAuth:
    def test_logged_out_filtered_profile_redirects_to_login(self, client):
        resp = client.get("/profile?start_date=2025-01-01&end_date=2025-12-31")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# GET /profile — filter bar markup                                    #
# ------------------------------------------------------------------ #


class TestFilterBar:
    def test_filter_bar_is_a_get_form_posting_to_profile(self, main_client):
        html = main_client.get("/profile").get_data(as_text=True)
        form = re.search(r"<form\b[^>]*>", html)
        assert form
        assert re.search(r'method="get"', form.group(0), re.I)
        assert 'action="/profile"' in form.group(0)
        assert re.search(
            r'<input[^>]*type="date"[^>]*name="start_date"'
            r'|<input[^>]*name="start_date"[^>]*type="date"',
            html,
        )
        assert re.search(
            r'<input[^>]*type="date"[^>]*name="end_date"'
            r'|<input[^>]*name="end_date"[^>]*type="date"',
            html,
        )
        text = page_text(html)
        for label in ("From", "To", "Apply", "This month", "Last 3 months", "All time"):
            assert label in text

    def test_filter_bar_sits_between_profile_card_and_stats(self, main_client):
        html = main_client.get("/profile").get_data(as_text=True)
        email_pos = html.index("filter@test.com")
        form_pos = html.index('name="start_date"')
        stats_pos = html.index("Total spent")
        assert email_pos < form_pos < stats_pos

    def test_preset_links_use_computed_ranges(self, main_client):
        today = date.today()
        html = main_client.get("/profile").get_data(as_text=True)
        this_month = preset_anchor(html, "This month")
        assert f"start_date={today.replace(day=1).isoformat()}" in this_month
        assert f"end_date={today.isoformat()}" in this_month
        last3 = preset_anchor(html, "Last 3 months")
        assert f"start_date={three_months_before(today).isoformat()}" in last3
        assert f"end_date={today.isoformat()}" in last3
        all_time = preset_anchor(html, "All time")
        assert 'href="/profile"' in all_time

    def test_no_inline_styles(self, main_client):
        html = main_client.get("/profile?start_date=2025-01-01").get_data(as_text=True)
        assert "<style" not in html
        assert 'style="' not in html


# ------------------------------------------------------------------ #
# GET /profile — filtering behaviour (fixed-date fixture user)        #
# ------------------------------------------------------------------ #


class TestProfileFiltering:
    def test_no_params_shows_all_time(self, main_client):
        resp = main_client.get("/profile")
        assert resp.status_code == 200
        text = page_text(resp.get_data(as_text=True))
        assert "Total spent ₹600.00" in text
        assert "Transactions 3" in text
        assert "Top category Shopping" in text
        assert "Showing all time" in text

    def test_empty_string_params_mean_no_filter(self, main_client):
        resp = main_client.get("/profile?start_date=&end_date=")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹600.00" in text
        assert "Transactions 3" in text
        assert INVALID_DATE_MSG not in html
        assert REVERSED_MSG not in html

    def test_range_filters_all_three_sections(self, main_client):
        resp = main_client.get("/profile?start_date=2025-02-01&end_date=2025-03-31")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹500.00" in text
        assert "Transactions 2" in text
        assert "Top category Shopping" in text
        assert "Feb electricity" in html and "Mar jacket" in html
        assert "Jan groceries" not in html
        assert "Food" not in text  # absent from table and breakdown

    def test_inputs_prefilled_with_applied_range(self, main_client):
        html = main_client.get("/profile?start_date=2025-02-01&end_date=2025-03-31").get_data(
            as_text=True
        )
        assert input_value(html, "start_date") == "2025-02-01"
        assert input_value(html, "end_date") == "2025-03-31"

    def test_inputs_empty_when_unfiltered(self, main_client):
        html = main_client.get("/profile").get_data(as_text=True)
        assert input_value(html, "start_date") == ""
        assert input_value(html, "end_date") == ""

    def test_active_range_label(self, main_client):
        html = main_client.get("/profile?start_date=2025-02-01&end_date=2025-03-31").get_data(
            as_text=True
        )
        text = page_text(html)
        assert "Showing" in text
        assert "1 Feb 2025" in text and "31 Mar 2025" in text
        assert "Showing all time" not in text

    def test_range_is_inclusive_on_both_ends(self, main_client):
        text = page_text(
            main_client.get("/profile?start_date=2025-01-10&end_date=2025-02-15").get_data(
                as_text=True
            )
        )
        assert "Total spent ₹300.00" in text
        assert "Transactions 2" in text

    def test_single_day_with_one_expense(self, main_client):
        html = main_client.get("/profile?start_date=2025-02-15&end_date=2025-02-15").get_data(
            as_text=True
        )
        text = page_text(html)
        assert "Total spent ₹200.00" in text
        assert "Transactions 1" in text
        assert "Top category Bills" in text
        assert "Feb electricity" in html

    def test_empty_range_shows_zero_state_and_empty_messages(self, main_client):
        resp = main_client.get("/profile?start_date=2024-01-01&end_date=2024-12-31")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹0.00" in text
        assert "Transactions 0" in text
        assert "Top category —" in text
        # empty state in both the transactions table and category breakdown
        assert html.count(EMPTY_MSG) >= 2

    def test_start_date_only_is_open_ended(self, main_client):
        resp = main_client.get("/profile?start_date=2025-02-01")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹500.00" in text
        assert "Transactions 2" in text
        assert "Jan groceries" not in html
        assert input_value(html, "start_date") == "2025-02-01"

    def test_end_date_only_is_open_ended(self, main_client):
        resp = main_client.get("/profile?end_date=2025-02-15")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹300.00" in text
        assert "Transactions 2" in text
        assert "Mar jacket" not in html
        assert input_value(html, "end_date") == "2025-02-15"

    def test_user_info_unaffected_by_filter(self, main_client):
        html = main_client.get("/profile?start_date=2024-01-01&end_date=2024-12-31").get_data(
            as_text=True
        )
        assert "Filter Tester" in html
        assert "filter@test.com" in html
        assert "Member since" in html

    def test_other_users_expenses_never_shown(self, main_client):
        for qs in (
            "",
            "?start_date=2025-01-01&end_date=2025-12-31",
            "?start_date=2025-02-15&end_date=2025-02-15",
        ):
            html = main_client.get(f"/profile{qs}").get_data(as_text=True)
            assert OTHER_USER_MARKER not in html
            assert "₹5000.00" not in html
            assert "Travel" not in html

    def test_currency_is_rupee(self, main_client):
        html = main_client.get("/profile?start_date=2025-01-01").get_data(as_text=True)
        assert "₹" in html
        assert "$" not in page_text(html)


# ------------------------------------------------------------------ #
# GET /profile — invalid input                                        #
# ------------------------------------------------------------------ #


class TestInvalidInput:
    @pytest.mark.parametrize(
        "qs",
        [
            "start_date=not-a-date",
            "end_date=not-a-date",
            "start_date=2025-13-01",
            "start_date=2025-02-30&end_date=2025-03-01",
            "start_date=2025-01-01&end_date=garbage",
        ],
    )
    def test_invalid_date_falls_back_to_unfiltered_with_message(self, main_client, qs):
        resp = main_client.get(f"/profile?{qs}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert INVALID_DATE_MSG in html
        text = page_text(html)
        assert "Total spent ₹600.00" in text
        assert "Transactions 3" in text

    def test_reversed_range_falls_back_to_unfiltered_with_message(self, main_client):
        resp = main_client.get("/profile?start_date=2026-09-20&end_date=2026-09-01")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert REVERSED_MSG in html
        text = page_text(html)
        assert "Total spent ₹600.00" in text
        assert "Transactions 3" in text

    def test_error_message_rendered_inside_filter_bar(self, main_client):
        html = main_client.get("/profile?start_date=not-a-date").get_data(as_text=True)
        assert (
            html.index('name="start_date"')
            < html.index(INVALID_DATE_MSG)
            < html.index("Total spent")
        )

    def test_sql_injection_attempt_is_treated_as_invalid(self, main_client):
        resp = main_client.get("/profile", query_string={"start_date": "2026-01-01' OR '1'='1"})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert INVALID_DATE_MSG in html
        assert OTHER_USER_MARKER not in html
        assert "₹5000.00" not in html
        assert "Transactions 3" in page_text(html)

    def test_valid_filter_shows_no_error(self, main_client):
        html = main_client.get("/profile?start_date=2025-01-01&end_date=2025-12-31").get_data(
            as_text=True
        )
        assert INVALID_DATE_MSG not in html
        assert REVERSED_MSG not in html


# ------------------------------------------------------------------ #
# GET /profile — presets (dates relative to date.today())             #
# ------------------------------------------------------------------ #


class TestPresets:
    def test_this_month_preset_filters_and_is_active(self, preset_client):
        today = date.today()
        resp = preset_client.get(
            "/profile",
            query_string={
                "start_date": today.replace(day=1).isoformat(),
                "end_date": today.isoformat(),
            },
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹30.00" in text
        assert "Transactions 2" in text
        assert is_active(preset_anchor(html, "This month"))
        assert not is_active(preset_anchor(html, "Last 3 months"))
        assert not is_active(preset_anchor(html, "All time"))

    def test_last_three_months_preset_filters_and_is_active(self, preset_client):
        today = date.today()
        resp = preset_client.get(
            "/profile",
            query_string={
                "start_date": three_months_before(today).isoformat(),
                "end_date": today.isoformat(),
            },
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹150.00" in text
        assert "Transactions 4" in text
        assert "too old" not in html
        assert is_active(preset_anchor(html, "Last 3 months"))
        assert not is_active(preset_anchor(html, "This month"))

    def test_all_time_preset_clears_filter_and_is_active(self, preset_client):
        html = preset_client.get("/profile").get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹310.00" in text
        assert "Transactions 5" in text
        assert "Showing all time" in text
        assert is_active(preset_anchor(html, "All time"))
        assert not is_active(preset_anchor(html, "This month"))

    def test_custom_range_marks_no_preset_active(self, preset_client):
        html = preset_client.get("/profile?start_date=2000-01-01&end_date=2000-01-02").get_data(
            as_text=True
        )
        for label in ("This month", "Last 3 months", "All time"):
            assert not is_active(preset_anchor(html, label))


# ------------------------------------------------------------------ #
# Definition of Done — seeded demo user                               #
# ------------------------------------------------------------------ #


class TestDemoUserDefinitionOfDone:
    def test_unfiltered_matches_step5_totals(self, demo_client):
        text = page_text(demo_client.get("/profile").get_data(as_text=True))
        assert "Total spent ₹4758.50" in text
        assert "Transactions 8" in text
        assert "Top category Shopping" in text

    def test_single_day_third_of_month(self, demo_client):
        day3 = date.today().replace(day=3).isoformat()
        html = demo_client.get(
            "/profile", query_string={"start_date": day3, "end_date": day3}
        ).get_data(as_text=True)
        text = page_text(html)
        assert "Total spent ₹1200.50" in text
        assert "Transactions 1" in text
        assert "Top category Bills" in text
        assert OTHER_USER_MARKER not in html

    def test_single_day_breakdown_is_one_full_bar(self, demo_client, app):
        demo_id = get_user_id("demo@spendly.com")
        day3 = date.today().replace(day=3).isoformat()
        cats = get_category_breakdown(demo_id, day3, day3)
        assert len(cats) == 1
        assert cats[0]["name"] == "Bills"
        assert cats[0]["percent"] == 100

    def test_this_month_preset_shows_current_month_seed_expenses(self, demo_client):
        today = date.today()
        seed = [
            (250.0, 1),
            (1200.50, 3),
            (89.0, 5),
            (450.0, 7),
            (599.0, 10),
            (1750.0, 14),
            (120.0, 18),
            (300.0, 21),
        ]
        in_range = [amt for amt, day in seed if day <= today.day]
        html = demo_client.get(
            "/profile",
            query_string={
                "start_date": today.replace(day=1).isoformat(),
                "end_date": today.isoformat(),
            },
        ).get_data(as_text=True)
        text = page_text(html)
        assert f"Total spent ₹{sum(in_range):.2f}" in text
        assert f"Transactions {len(in_range)}" in text
        assert is_active(preset_anchor(html, "This month"))
        assert OTHER_USER_MARKER not in html
