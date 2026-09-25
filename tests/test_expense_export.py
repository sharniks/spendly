"""Tests for the CSV export feature (GET /expenses/export).

Derived from openspec/changes/export-expenses-csv/specs/expense-export/spec.md
(requirements and scenarios) and design.md (get_all_transactions helper). All
data lives in an isolated temp SQLite DB (see tests/conftest.py); the
`client` fixture is provided by pytest-flask from the `app` fixture in
conftest.py.
"""

import csv
import io
import re

import pytest

import database.db as db_module
from database.queries import get_all_transactions

DEMO_EMAIL = "demo@spendly.com"
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


def login_as(client, user_id, name="Test User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name


def parse_csv(response_data):
    text = response_data.decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def users(app):
    """A main user with fixed 2025 expenses and a second user with
    expenses on the same dates (for data-isolation checks)."""
    main_id = db_module.create_user("Export Tester", "export@test.com", "x-hash")
    other_id = db_module.create_user("Other Person", "other@test.com", "x-hash")

    insert_expense(main_id, 100.0, "Food", "2025-01-10", "Jan groceries")
    insert_expense(main_id, 200.0, "Bills", "2025-02-15", "Feb electricity")
    insert_expense(main_id, 300.0, "Shopping", "2025-03-20", "Mar jacket")

    for d in ("2025-01-10", "2025-02-15", "2025-03-20"):
        insert_expense(other_id, 5000.0, "Travel", d, OTHER_USER_MARKER)

    return {"main": main_id, "other": other_id}


@pytest.fixture
def main_client(client, users):
    login_as(client, users["main"], "Export Tester")
    return client


# ------------------------------------------------------------------ #
# get_all_transactions (database/queries.py)                          #
# ------------------------------------------------------------------ #


class TestGetAllTransactions:
    def test_unfiltered_returns_all_rows_oldest_first(self, users):
        txs = get_all_transactions(users["main"])
        assert [t["date"] for t in txs] == ["2025-01-10", "2025-02-15", "2025-03-20"]

    def test_start_date_only_is_open_ended(self, users):
        txs = get_all_transactions(users["main"], start_date="2025-02-01")
        assert [t["date"] for t in txs] == ["2025-02-15", "2025-03-20"]

    def test_end_date_only_is_open_ended(self, users):
        txs = get_all_transactions(users["main"], end_date="2025-02-15")
        assert [t["date"] for t in txs] == ["2025-01-10", "2025-02-15"]

    def test_both_bounds_are_inclusive(self, users):
        txs = get_all_transactions(users["main"], start_date="2025-01-10", end_date="2025-02-15")
        assert [t["date"] for t in txs] == ["2025-01-10", "2025-02-15"]

    def test_range_with_no_matches_returns_empty_list(self, users):
        assert get_all_transactions(users["main"], "2024-01-01", "2024-12-31") == []

    def test_user_with_no_expenses_returns_empty_list(self, app):
        uid = db_module.create_user("Empty User", "empty@test.com", "x-hash")
        assert get_all_transactions(uid) == []

    def test_never_includes_other_users_expenses(self, users):
        txs = get_all_transactions(users["main"])
        assert all(t["description"] != OTHER_USER_MARKER for t in txs)


# ------------------------------------------------------------------ #
# GET /expenses/export                                                #
# ------------------------------------------------------------------ #


class TestExportRoute:
    def test_logged_out_redirects_to_login(self, client):
        resp = client.get("/expenses/export")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_unfiltered_export_contains_only_own_rows(self, main_client, users):
        resp = main_client.get("/expenses/export")
        assert resp.status_code == 200
        rows = parse_csv(resp.data)
        body_rows = rows[1:]
        assert len(body_rows) == 3
        assert all(OTHER_USER_MARKER not in row for row in body_rows)

    def test_content_type_and_disposition_trigger_download(self, main_client):
        resp = main_client.get("/expenses/export")
        assert resp.headers["Content-Type"].startswith("text/csv")
        assert "attachment" in resp.headers["Content-Disposition"]

    def test_date_range_filtering_matches_inclusive_bounds(self, main_client):
        resp = main_client.get("/expenses/export?start_date=2025-01-10&end_date=2025-02-15")
        rows = parse_csv(resp.data)
        dates = [row[0] for row in rows[1:]]
        assert dates == ["2025-01-10", "2025-02-15"]

    def test_invalid_date_falls_back_to_unfiltered(self, main_client):
        resp = main_client.get("/expenses/export?start_date=not-a-date")
        assert resp.status_code == 200
        rows = parse_csv(resp.data)
        assert len(rows) - 1 == 3

    def test_reversed_dates_fall_back_to_unfiltered(self, main_client):
        resp = main_client.get(
            "/expenses/export?start_date=2025-09-20&end_date=2025-01-01"
        )
        assert resp.status_code == 200
        rows = parse_csv(resp.data)
        assert len(rows) - 1 == 3

    def test_range_with_no_matches_returns_header_only(self, main_client):
        resp = main_client.get(
            "/expenses/export?start_date=2024-01-01&end_date=2024-12-31"
        )
        assert resp.status_code == 200
        rows = parse_csv(resp.data)
        assert rows == [["Date", "Category", "Description", "Amount"]]

    def test_csv_columns_and_ordering(self, main_client):
        resp = main_client.get("/expenses/export")
        rows = parse_csv(resp.data)
        assert rows[0] == ["Date", "Category", "Description", "Amount"]
        dates = [row[0] for row in rows[1:]]
        assert dates == sorted(dates)

    def test_null_description_exports_as_empty_field(self, main_client, users):
        insert_expense(users["main"], 50.0, "Other", "2025-04-01", None)
        resp = main_client.get("/expenses/export")
        rows = parse_csv(resp.data)
        row = next(r for r in rows[1:] if r[0] == "2025-04-01")
        assert row[2] == ""
