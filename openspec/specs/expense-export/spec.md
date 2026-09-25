# expense-export Specification

## Purpose

Lets a logged-in user download their own expenses, optionally limited to a
date range, as a CSV file for offline use, backup, or reconciliation outside
the app.

## Requirements

### Requirement: Authenticated CSV export of own expenses
The system SHALL provide a `GET /expenses/export` route that returns the
logged-in user's expenses as a downloadable CSV file. The route SHALL only
ever include expenses owned by the requesting user.

#### Scenario: Logged-in user exports all expenses
- **WHEN** a logged-in user requests `GET /expenses/export` with no query
  parameters
- **THEN** the system returns a CSV file (as an attachment download, not
  rendered inline) containing every expense belonging to that user

#### Scenario: Anonymous user is redirected
- **WHEN** a user with no active session requests `GET /expenses/export`
- **THEN** the system redirects to `/login` and does not return any expense
  data

#### Scenario: Export never includes another user's expenses
- **WHEN** a logged-in user requests `GET /expenses/export`
- **THEN** the CSV contains only rows where the expense belongs to the
  requesting user, even if other users have expenses in the same date range

### Requirement: Export respects the profile date-range filter
`GET /expenses/export` SHALL accept the same optional `start_date` and
`end_date` query parameters (inclusive range, `YYYY-MM-DD`) as `GET
/profile`, and SHALL apply the same validation and interpretation rules
already defined for the profile date filter.

#### Scenario: Export limited to a date range
- **WHEN** a logged-in user requests `GET /expenses/export?start_date=2026-09-01&end_date=2026-09-30`
- **THEN** the CSV contains only expenses whose date falls within that
  inclusive range

#### Scenario: Export with only one bound supplied
- **WHEN** a logged-in user requests `GET /expenses/export` with only
  `start_date` or only `end_date` set
- **THEN** the CSV contains only expenses on or after `start_date`, or only
  expenses on or before `end_date`, respectively

#### Scenario: Invalid date parameters fall back to unfiltered export
- **WHEN** a logged-in user requests `GET /expenses/export` with a
  `start_date` or `end_date` that is not a valid `YYYY-MM-DD` date, or with
  `start_date` after `end_date`
- **THEN** the system returns a 200 response with a CSV of the user's
  unfiltered (all-time) expenses rather than erroring, matching how
  `/profile` falls back to the unfiltered view on invalid input

#### Scenario: Date range with no matching expenses
- **WHEN** a logged-in user requests `GET /expenses/export` with a date
  range that matches none of their expenses
- **THEN** the system returns a 200 response with a CSV file containing only
  the header row

### Requirement: CSV content and format
The exported CSV SHALL contain one header row followed by one row per
matching expense, with columns Date, Category, Description, and Amount. Rows
SHALL be ordered oldest-first by date. Amount values SHALL be plain decimal
numbers (no currency symbol) suitable for spreadsheet import.

#### Scenario: CSV columns and ordering
- **WHEN** a logged-in user with multiple expenses across different dates
  requests `GET /expenses/export`
- **THEN** the returned CSV's header row reads `Date,Category,Description,Amount`
  and the data rows are ordered from oldest expense date to newest

#### Scenario: Expense with no description exports cleanly
- **WHEN** a user's expense has no description (null/empty)
- **THEN** the corresponding CSV row has an empty Description field and does
  not error
