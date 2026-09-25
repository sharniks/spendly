# Design

## Context

`app.py` already has `parse_date_range(start_arg, end_arg)` used by
`profile()` to validate/interpret `start_date`/`end_date` query params,
falling back to `(None, None, error_message)` on invalid input. `queries.py`
has `get_recent_transactions(user_id, limit=10, start_date=None,
end_date=None)`, which is capped at `limit` rows and ordered newest-first —
wrong shape for an export that needs every matching row. See proposal.md -
Why / What Changes for motivation.

## Goals / Non-Goals

**Goals:**
- Reuse the existing date-range parsing/validation behavior exactly, so
  export and the profile page agree on what a given URL means
- Keep the export route thin: parse params, fetch rows, write CSV, done

**Non-Goals:**
- No new export formats (PDF, Excel) — CSV only
- No async/background job — the row counts here are small (personal expense
  tracker), so synchronous generation on request is fine
- No changes to `get_recent_transactions` — it stays limited/newest-first for
  the profile page; export uses its own helper

## Decisions

**New query helper instead of reusing/modifying `get_recent_transactions`.**
Add `get_all_transactions(user_id, start_date=None, end_date=None)` to
`database/queries.py`, mirroring the same optional-range `WHERE` clause
pattern (`AND date >= ?` / `AND date <= ?`) but with no `LIMIT` and ordered
`date ASC` (oldest-first, natural spreadsheet reading order) instead of
`date DESC`. Alternative considered: add a `limit=None` escape hatch to
`get_recent_transactions`. Rejected — that function's name and every
existing caller assume "recent, capped, newest-first"; overloading it with
an unbounded/reordered mode is a surprising side door rather than a clear
contract.

**Build the CSV in-memory with `csv.writer` + `io.StringIO`, return via
`Response` with `Content-Disposition: attachment`.** Personal-expense-tracker
row counts are small (tens to low thousands), so there's no need for
streaming. This is the standard Flask pattern for CSV download and needs no
new dependency.

**Route reuses `parse_date_range()` from `app.py` directly**, not a copy.
Same function, same behavior as `/profile`, so a bookmarked filtered
`/profile?start_date=...&end_date=...` URL and its corresponding export
agree byte-for-byte on what rows are "in range." No new date-parsing code.

**Route placement: `GET /expenses/export`, not `GET /profile/export`.** Follows
the existing `/expenses/<id>/...` family (`/expenses/add`,
`/expenses/<id>/edit`, `/expenses/<id>/delete`) as the namespace for
expense-related actions, even though it's reached from the profile page.

## Risks / Trade-offs

- **[Risk]** Large future expense volume could make in-memory CSV generation
  slow. → **Mitigation**: not a concern at current/expected personal-tracker
  scale; revisit only if it becomes one.
- **[Risk]** Filename collisions or missing `Content-Disposition` in some
  browser could render the CSV inline instead of downloading. → **Mitigation**:
  set both `Content-Disposition: attachment; filename=...` and
  `Content-Type: text/csv` explicitly on the response.
