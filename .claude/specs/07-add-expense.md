# Spec: Add Expense

## Overview
This feature implements the `GET /expenses/add` and `POST /expenses/add` routes,
replacing the current stub. It lets a logged-in user submit a new expense
(amount, category, date, optional description) via a form, which is validated
and persisted to the `expenses` table. On success the user is redirected back
to their profile page, where the new expense immediately appears in the
recent transactions list, category breakdown, and summary stats. This is the
first step in the roadmap where users can create data themselves, rather than
only viewing seeded data.

## Depends on
- Step 01 (Database setup) — `expenses` table must exist
- Step 03 (Login/Logout) — route requires an authenticated session
- Step 04/05 (Profile page + backend) — redirect target and the queries that
  render newly added expenses

## Routes
- `GET /expenses/add` — renders the add-expense form — logged-in only
- `POST /expenses/add` — validates form input, inserts the expense, redirects
  to `/profile` — logged-in only

Both routes must redirect anonymous users to `/login`, matching the pattern
already used in `profile()`.

## Database changes
No database changes. The `expenses` table (`database/db.py`) already has the
required columns: `user_id`, `amount`, `category`, `date`, `description`.

A new function `create_expense(user_id, amount, category, expense_date, description)`
must be added to `database/db.py`, following the same connect/try/finally
pattern as `create_user`. It must use a parameterized `INSERT` and return
`cursor.lastrowid`.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`, contains
  the add-expense form. Follows the same structure as `templates/register.html`
  (form-group / form-input / btn-submit classes, error banner at top of card).
- **Modify:** None. `templates/profile.html` already renders expenses from
  the DB and needs no changes — new expenses will appear automatically once
  inserted.

A link/button to `/expenses/add` should be added to `templates/profile.html`
using `url_for('add_expense')` (e.g. near the transactions list), since there
is currently no way to reach the form from the UI.

## Files to change
- `app.py` — replace the `add_expense` stub with real `GET`/`POST` handling
- `database/db.py` — add `create_expense()`
- `templates/profile.html` — add a link/button to the add-expense page

## Files to create
- `templates/add_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders)
- Passwords hashed with werkzeug (n/a to this feature, but keep convention if touched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives only in `database/db.py`, never inline in `app.py`
- Validate `amount` (must be a positive number) and `category` (must be
  non-empty) server-side; re-render the form with an error message on
  failure, matching the `register()` pattern — never a bare string return
- `date` input must be validated as `YYYY-MM-DD` using the existing
  `parse_iso_date()` helper in `app.py`; default to today's date if blank
- Amounts are in INR (₹) — match existing formatting conventions used on
  the profile page
- Use `url_for()` for all internal links, including the form's `action`

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with fields
      for amount, category, date, and description
- [ ] Submitting the form with valid data creates a new row in `expenses`
      with the correct `user_id`
- [ ] After submitting, the browser redirects to `/profile`
- [ ] The new expense appears in the recent transactions list and is
      reflected in the summary stats and category breakdown on `/profile`
- [ ] Submitting with a missing/zero/negative amount re-renders the form
      with a validation error and does not insert a row
- [ ] Submitting with an empty category re-renders the form with a
      validation error and does not insert a row
- [ ] Submitting with an invalid date format re-renders the form with a
      validation error and does not insert a row
- [ ] `profile.html` has a working link to `/expenses/add` using `url_for()`
