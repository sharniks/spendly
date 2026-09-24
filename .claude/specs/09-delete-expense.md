# Spec: Delete Expense

## Overview
This feature implements the `GET /expenses/<id>/delete` and
`POST /expenses/<id>/delete` routes, replacing the current stub. It lets a
logged-in user permanently remove an expense they own from their profile.
The current stub only accepts `GET`, but a destructive action must not be
triggerable by a simple link click or crawler — so `GET` will render a
confirmation page, and the actual deletion will happen on `POST`. This is
the third and final step in the expense-mutation trio (add → edit → delete),
completing full CRUD for expenses, and it reuses the same ownership-check
pattern introduced in edit-expense.

## Depends on
- Step 01 (Database setup) — `expenses` table must exist
- Step 03 (Login/Logout) — route requires an authenticated session
- Step 04/05 (Profile page + backend) — redirect target after deletion
- Step 08 (Edit expense) — reuses `get_expense_by_id()` and the
  fetch-then-ownership-check pattern already established in `edit_expense()`

## Routes
- `GET /expenses/<id>/delete` — renders a confirmation page showing the
  expense's details and a "Delete" button that submits a `POST` — logged-in
  only, owner only
- `POST /expenses/<id>/delete` — deletes the expense, redirects to
  `/profile` — logged-in only, owner only

Both routes must redirect anonymous users to `/login`, matching the pattern
already used in `profile()`, `add_expense()`, and `edit_expense()`.

If the expense does not exist, or exists but belongs to a different user,
respond with `abort(404)` — do not reveal whether the expense exists for
another account.

## Database changes
No schema changes. The `expenses` table (`database/db.py`) already has the
required columns.

One new function must be added to `database/db.py`, following the same
connect/try/finally pattern as `update_expense`:

- `delete_expense(expense_id)` — parameterized
  `DELETE FROM expenses WHERE id = ?`. No return value needed. Ownership is
  checked in the route beforehand, not in this helper (mirrors
  `update_expense`).

## Templates
- **Create:** `templates/delete_expense.html` — extends `base.html`. Shows
  the expense's date, category, description, and amount (₹) as read-only
  summary, a warning that this cannot be undone, a "Delete" submit button
  (form posts to `url_for('delete_expense', id=expense.id)`), and a "Cancel"
  link back to `url_for('profile')`.
- **Modify:** `templates/profile.html` — add a "Delete" link next to the
  existing "Edit" link in the `tx-actions-col` of each `tx-table` row,
  pointing to `url_for('delete_expense', id=tx.id)`.

## Files to change
- `app.py` — replace the `delete_expense` stub with real `GET`/`POST`
  handling
- `database/db.py` — add `delete_expense()`
- `templates/profile.html` — add a delete link per transaction row

## Files to create
- `templates/delete_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders)
- Passwords hashed with werkzeug (n/a to this feature, but keep convention if touched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives only in `database/db.py`, never inline in `app.py`
- Reuse `get_expense_by_id()` already defined in `database/db.py` — do not
  redefine it
- Deletion must never happen on `GET` — `GET` only renders the confirmation
  page; the actual `DELETE FROM expenses` only runs on `POST`
- Ownership check: fetch the expense, `abort(404)` if it doesn't exist or
  `expense["user_id"] != session["user_id"]`, before rendering the `GET`
  confirmation page or applying the `POST` deletion
- Amounts are in INR (₹) — match existing formatting conventions used on
  the profile, add-expense, and edit-expense pages
- Use `url_for()` for all internal links, including the confirmation form's
  `action`, the "Cancel" link, and the new delete link on `profile.html`
- No JS confirm()/alert() dialogs required — the confirmation page itself
  is the confirmation step; keep `static/js/main.js` untouched unless a
  client-side enhancement is explicitly requested later

## Definition of done
- [ ] Visiting `/expenses/<id>/delete` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/delete` for an expense that doesn't exist returns 404
- [ ] Visiting `/expenses/<id>/delete` for another user's expense returns 404
- [ ] Visiting `/expenses/<id>/delete` for your own expense renders a
      confirmation page showing its date, category, description, and amount
- [ ] A `GET` request never deletes the row — the expense still exists in
      the database afterward
- [ ] Submitting the confirmation form (`POST`) deletes the row from
      `expenses` and does not affect other users' or other expenses' rows
- [ ] After submitting, the browser redirects to `/profile`
- [ ] The deleted expense no longer appears in the recent transactions list
      and is excluded from the summary stats and category breakdown on
      `/profile`
- [ ] `profile.html` has a working delete link per transaction row using
      `url_for()`
