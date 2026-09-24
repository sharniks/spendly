# Spec: Edit Expense

## Overview
This feature implements the `GET /expenses/<id>/edit` and
`POST /expenses/<id>/edit` routes, replacing the current stub. It lets a
logged-in user modify an existing expense they own (amount, category, date,
description) via a pre-filled form, validated the same way as the add-expense
form, and persisted back to the `expenses` table. On success the user is
redirected to their profile page, where the updated expense is reflected
immediately. This is the second step in the roadmap where users mutate
existing data, following the add-expense flow, and it introduces ownership
checks since a user must only be able to edit their own expenses.

## Depends on
- Step 01 (Database setup) — `expenses` table must exist
- Step 03 (Login/Logout) — route requires an authenticated session
- Step 04/05 (Profile page + backend) — redirect target and the queries that
  render the updated expense
- Step 07 (Add expense) — reuses `EXPENSE_CATEGORIES`, `MAX_EXPENSE_AMOUNT`,
  `MAX_DESCRIPTION_LENGTH`, `parse_iso_date()`, and the add-expense form
  structure/validation pattern

## Routes
- `GET /expenses/<id>/edit` — renders the edit-expense form pre-filled with
  the expense's current values — logged-in only, owner only
- `POST /expenses/<id>/edit` — validates form input, updates the expense,
  redirects to `/profile` — logged-in only, owner only

Both routes must redirect anonymous users to `/login`, matching the pattern
already used in `profile()` and `add_expense()`.

If the expense does not exist, or exists but belongs to a different user,
respond with `abort(404)` — do not reveal whether the expense exists for
another account.

## Database changes
No schema changes. The `expenses` table (`database/db.py`) already has the
required columns: `id`, `user_id`, `amount`, `category`, `date`,
`description`.

Two new functions must be added to `database/db.py`, following the same
connect/try/finally pattern as `create_expense`:

- `get_expense_by_id(expense_id)` — `SELECT * FROM expenses WHERE id = ?`,
  returns a single row or `None`. Ownership is checked in the route, not
  in this helper (mirrors how `get_user_by_id` is a plain lookup).
- `update_expense(expense_id, amount, category, expense_date, description)`
  — parameterized `UPDATE`, sets `amount`, `category`, `date`, `description`
  for the given `id`. No return value needed.

`database/queries.py` — `get_recent_transactions()` currently selects
`date, description, category, amount` only. Add `id` to the `SELECT` list
so `templates/profile.html` can link each row to its edit page.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`, near-
  identical to `templates/add_expense.html` (same form-group / form-input /
  btn-submit classes, error banner). Differences: page title "Edit expense",
  form fields pre-filled from the existing expense on `GET`, form `action`
  points to `url_for('edit_expense', id=expense.id)`, submit button reads
  "Save changes".
- **Modify:** `templates/profile.html` — add an "Edit" link on each row of
  the `tx-table` (new column or inline action) pointing to
  `url_for('edit_expense', id=tx.id)`. The `{% for tx in transactions %}`
  loop already has access to each transaction dict; it will now include `id`
  once the query change above lands.

## Files to change
- `app.py` — replace the `edit_expense` stub with real `GET`/`POST` handling
- `database/db.py` — add `get_expense_by_id()` and `update_expense()`
- `database/queries.py` — add `id` to `get_recent_transactions()`'s `SELECT`
- `templates/profile.html` — add an edit link per transaction row

## Files to create
- `templates/edit_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders)
- Passwords hashed with werkzeug (n/a to this feature, but keep convention if touched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives only in `database/db.py`, never inline in `app.py`
- Reuse `EXPENSE_CATEGORIES`, `MAX_EXPENSE_AMOUNT`, `MAX_DESCRIPTION_LENGTH`,
  and `parse_iso_date()` already defined in `app.py` — do not redefine them
- Validate `amount` (positive number, within `MAX_EXPENSE_AMOUNT`) and
  `category` (must be one of `EXPENSE_CATEGORIES`) server-side; re-render
  the form with an error message on failure, matching the `add_expense()`
  pattern — never a bare string return
- `date` input must be validated as `YYYY-MM-DD` using `parse_iso_date()`
- Ownership check: fetch the expense, `abort(404)` if it doesn't exist or
  `expense["user_id"] != session["user_id"]`, before rendering the `GET`
  form or applying the `POST` update
- Amounts are in INR (₹) — match existing formatting conventions used on
  the profile and add-expense pages
- Use `url_for()` for all internal links, including the form's `action` and
  the new edit link on `profile.html`

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense that doesn't exist returns 404
- [ ] Visiting `/expenses/<id>/edit` for another user's expense returns 404
- [ ] Visiting `/expenses/<id>/edit` for your own expense renders a form
      pre-filled with its current amount, category, date, and description
- [ ] Submitting the form with valid changes updates the row in `expenses`
      and does not change its `id` or `user_id`
- [ ] After submitting, the browser redirects to `/profile`
- [ ] The updated values appear in the recent transactions list and are
      reflected in the summary stats and category breakdown on `/profile`
- [ ] Submitting with a missing/zero/negative amount re-renders the form
      with a validation error and does not modify the row
- [ ] Submitting with an invalid category re-renders the form with a
      validation error and does not modify the row
- [ ] Submitting with an invalid date format re-renders the form with a
      validation error and does not modify the row
- [ ] `profile.html` has a working edit link per transaction row using
      `url_for()`
