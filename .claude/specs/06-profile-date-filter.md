# Spec: Date Filter for Profile Page

## Overview

Step 6 lets a logged-in user narrow the profile page to a date range. Right
now `/profile` always shows lifetime totals: every expense in the summary
stats, the 10 most recent transactions, and the full category breakdown. This
step adds a small filter bar above the stats, with a "From" date, a "To" date
and quick presets (This month, Last 3 months, All time). The chosen range is
passed as query-string parameters on the existing `GET /profile` route, and
all three data sections (summary stats, recent transactions, category
breakdown) respect it. The filter uses a plain HTML `GET` form, so it works
without JavaScript, and a filtered view can be bookmarked or shared as a URL.

## Depends on

- Step 1: Database setup (`expenses.date` stored as `YYYY-MM-DD` text)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 4: Profile page static UI
- Step 5: Profile page backend (`database/queries.py` helpers exist and feed `/profile`)

## Routes

No new routes. The existing `GET /profile` route is modified to accept two
optional query-string parameters:

- `GET /profile?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` — renders the
  profile page limited to expenses whose `date` falls in the inclusive range —
  logged-in

Parameter behaviour:

- Both parameters are optional. Omitting one leaves that side of the range open
  (e.g. only `start_date` means "from this date onward").
- Omitting both (or passing empty strings) means no filter, which is the current
  behaviour.
- A value that is not a valid `YYYY-MM-DD` date is ignored. The page renders
  unfiltered and shows an inline error message ("Invalid date — showing all
  expenses."). It must never return a 500.
- If `start_date` is after `end_date`, the page renders unfiltered and shows an
  inline error message ("Start date must be on or before end date.").

## Database changes

No database changes. `expenses.date` is already stored as `YYYY-MM-DD` TEXT,
which sorts and compares correctly with SQLite string comparison
(`date >= ?` / `date <= ?`).

## Templates

- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter bar (`<form method="get" action="{{ url_for('profile') }}">`)
    between the profile card and the stats tiles, containing:
    - `<input type="date" name="start_date">` labelled "From", pre-filled with
      the active `start_date`
    - `<input type="date" name="end_date">` labelled "To", pre-filled with the
      active `end_date`
    - An "Apply" submit button
    - Preset links built with `url_for('profile', start_date=..., end_date=...)`:
      "This month", "Last 3 months", "All time" (`url_for('profile')` with no
      params)
  - Mark the currently active preset (if any) with an `is-active` class
  - Show a line such as "Showing 1 Sep 2026 – 22 Sep 2026" when a filter is
    active, or "Showing all time" otherwise
  - Render the filter error message (if any) inside the filter bar
  - When the filtered range has no expenses, show an empty-state row in the
    transactions table ("No expenses in this period.") and an empty-state
    message in the category breakdown, instead of an empty table/section

## Files to change

- `app.py` — `profile()` reads `start_date` / `end_date` from `request.args`,
  validates them, computes preset ranges, and passes the range to the query
  helpers and the template
- `database/queries.py` — add optional `start_date=None, end_date=None`
  parameters to `get_summary_stats`, `get_recent_transactions` and
  `get_category_breakdown`, and apply them as `AND date >= ?` / `AND date <= ?`
  clauses only when provided
- `templates/profile.html` — filter bar, active-range label, empty states
- `static/css/profile.css` — styles for the filter bar, preset pills, active
  state and error message

## Files to create

None.

## New dependencies

No new dependencies. Date parsing uses the standard library (`datetime.date.fromisoformat` / `datetime.strptime`).

## Rules for implementation

- No SQLAlchemy or ORMs. Use raw `sqlite3` only, via `get_db()`
- Parameterised queries only. Build the optional `WHERE` clauses by appending
  fixed SQL fragments (`" AND date >= ?"`) and pushing the value onto the params
  list. Never interpolate the date value into the SQL string
- Passwords hashed with werkzeug (unchanged by this step, but must not regress)
- Use CSS variables. Never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags or `style=""` attributes. Put new styles in `static/css/profile.css`
- Vanilla HTML form only. No JavaScript is required for the filter to work
- All internal links and the form `action` use `url_for()`, never hardcoded `/profile?...`
- Date validation lives in `app.py` (or a small helper function there). DB
  logic stays in `database/queries.py`
- Query helpers keep backward-compatible signatures. Calling them with only
  `user_id` must behave exactly as in Step 5 (unfiltered)
- The range is inclusive on both ends
- "This month" = first day of the current month through today. "Last 3
  months" = the day 3 calendar months before today through today (clamp to
  a valid day, e.g. 31 May → 28/29 Feb). Compute from `date.today()`
- User info (name, email, member since) is never affected by the filter
- Currency always displays as ₹
- Invalid or reversed dates must never raise. They fall back to the unfiltered
  view with an error message

## Definition of done

- [ ] Logged in as demo@spendly.com / demo123, `/profile` with no query
      params shows the same totals as before Step 6 (8 transactions, ₹4758.50
      total, "Shopping" top category)
- [ ] The filter bar with From/To date inputs, an Apply button and the three
      presets appears between the profile card and the stat tiles
- [ ] Choosing a From and To date and clicking Apply reloads `/profile` with
      `?start_date=...&end_date=...` in the URL, and the stats, transaction list
      and category breakdown only reflect expenses in that range
- [ ] The date inputs stay pre-filled with the applied range after reload
- [ ] Filtering to a single day that has exactly one seed expense (e.g. the 3rd
      of the current month) shows 1 transaction, that expense's amount as total
      spent, its category as top category, and a single 100% category bar
- [ ] Filtering to a range with no expenses shows ₹0.00, 0 transactions, "—"
      top category, and the empty-state messages. No errors
- [ ] Supplying only `start_date` or only `end_date` applies an open-ended range
- [ ] "This month" preset shows all current-month seed expenses and is
      highlighted as active
- [ ] "All time" preset clears the filter and returns to the unfiltered view
- [ ] `/profile?start_date=not-a-date` returns 200, shows the unfiltered view,
      and displays "Invalid date — showing all expenses."
- [ ] `/profile?start_date=2026-09-20&end_date=2026-09-01` returns 200, shows
      the unfiltered view, and displays "Start date must be on or before end date."
- [ ] `/profile?start_date=2026-01-01' OR '1'='1` does not error or leak other
      users' data (it is treated as an invalid date)
- [ ] Visiting `/profile?start_date=...` while logged out still redirects to `/login`
- [ ] A second user's expenses never appear in the demo user's filtered view
- [ ] The page renders correctly with no JavaScript enabled
