# Proposal

## Why

Every expense a user has entered is trapped inside the Spendly UI — there's no
way to get it out. Users who want to reconcile against a bank statement,
build their own spreadsheet analysis, or just keep an offline backup have no
option today. The app already computes a filtered expense list on `/profile`
(Step 6's date-range filter), so the data users most want to export — "my
expenses for this range" — is already one query away.

## What Changes

- Add a "Export CSV" link/button on the profile page, next to the existing
  filter bar, that downloads the currently filtered expense list as a `.csv`
  file
- Add a new `GET /expenses/export` route that streams a CSV file
  (`Content-Disposition: attachment`) of the logged-in user's expenses,
  honoring the same optional `start_date`/`end_date` query parameters as
  `/profile`
- Add a new DB helper in `database/queries.py` that returns **all** matching
  expenses (not the 10-row-limited `get_recent_transactions`), ordered
  oldest-first for a natural spreadsheet reading order
- CSV columns: Date, Category, Description, Amount (INR)

## Capabilities

### New Capabilities
- `expense-export`: lets a logged-in user download their own expenses (optionally
  filtered by date range) as a CSV file

### Modified Capabilities
(none — this reuses the existing date-filter query contract from `/profile`
without changing its behavior)

## Impact

- **`app.py`**: new `GET /expenses/export` route; reuses the existing
  `parse_date_range()` helper already defined for `/profile`
- **`database/queries.py`**: new `get_all_transactions(user_id, start_date=None, end_date=None)`
  helper (or similarly named), following the same optional-range pattern as
  `get_recent_transactions`
- **`templates/profile.html`**: one new link/button in the filter bar area
- **`static/css/profile.css`**: minor styling for the new export control
- No new dependencies — CSV generation uses Python's standard library `csv`
  module
- No schema changes
