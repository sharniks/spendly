# Tasks

## 1. Database helper

- [x] 1.1 Add `get_all_transactions(user_id, start_date=None, end_date=None)`
      to `database/queries.py`, mirroring the optional `AND date >= ?` / `AND
      date <= ?` pattern used in `get_recent_transactions` and
      `get_summary_stats`, but with no `LIMIT` and ordered `date ASC`. Verify
      with a quick manual call against the seeded demo user returning all 8
      rows oldest-first.
- [x] 1.2 Write unit tests for `get_all_transactions` covering: no filter
      (all rows, oldest-first), `start_date` only, `end_date` only, both
      bounds, a range matching zero rows (returns `[]`), and a user with no
      expenses. Verify with `pytest -k get_all_transactions`.

## 2. Export route

- [x] 2.1 Add `GET /expenses/export` to `app.py`: redirect to `/login` if no
      session; reuse `parse_date_range()` for `start_date`/`end_date` query
      params (on invalid/reversed dates, fall back to the unfiltered range
      rather than showing an error, per spec); call
      `get_all_transactions(user_id, start_iso, end_iso)`. Verify by hitting
      the route while logged in and confirming a 200 response.
- [x] 2.2 Build the CSV response using `csv.writer` over `io.StringIO` with
      header `Date,Category,Description,Amount`, one row per expense
      (Description empty string when null, Amount as plain decimal), and
      return a Flask `Response` with `Content-Type: text/csv` and
      `Content-Disposition: attachment; filename=expenses.csv`. Verify by
      downloading and opening the file, confirming header + row format.
- [x] 2.3 Write route tests in `tests/test_expense_export.py` covering: logged-out
      redirect to `/login`; unfiltered export contains only the requesting
      user's rows even when another seeded user has expenses; date-range
      filtering matches `/profile`'s inclusive-range behavior; invalid date
      falls back to unfiltered (200, not an error); reversed start/end falls
      back to unfiltered; a range matching no expenses returns a
      header-only CSV; CSV column order and oldest-first row order; a null
      description exports as an empty field. Verify with `pytest
      tests/test_expense_export.py`.

## 3. Profile page integration

- [x] 3.1 Add an "Export CSV" link in `templates/profile.html`'s filter bar
      area, built with `url_for('export_expenses', start_date=start_date,
      end_date=end_date)` so the exported file matches whatever range is
      currently applied. Verify by loading `/profile` with a filter active
      and confirming the link's href carries the same query params.
- [x] 3.2 Style the export link in `static/css/profile.css` using existing
      CSS variables, consistent with the preset-pill/filter-bar styling
      already in that file. Verify visually by loading `/profile` in a
      browser.

## 4. End-to-end verification

- [x] 4.1 Run the full test suite (`pytest`) and confirm no regressions in
      `tests/test_profile_date_filter.py` or other existing tests.
- [x] 4.2 Manually verify in the running app (`python app.py`, port 5001):
      log in as demo@spendly.com, apply a date filter on `/profile`, click
      "Export CSV", and confirm the downloaded file's rows match exactly
      the transactions shown in the filtered profile view.
