# Spec: Registration

## Overview

Implement user registration so that visitors can create a Spendly account. Currently `GET /register` only renders `register.html` — there is no `POST` handler, so the existing form submits into a 405. This step adds the `POST /register` handler that validates input, hashes the password, inserts a new row into `users`, and redirects the user into the app. On success the user is shown with a sucess message and then redirected to the login page. This builds directly on the data layer from Step 1 (`database/db.py`) and is a prerequisite for login (existing stub) and any authenticated routes (profile, expenses).

## Depends on

- Step 1 — Database setup (`database/db.py`: `get_db()`, `init_db()`, `users` table) — complete

## Routes

- `GET /register` — renders the registration form — public (already implemented, unchanged)
- `POST /register` — validates submitted form data, creates the user, redirects on success or re-renders the form with an error — public

## Database changes

No database changes. The `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) already supports registration as defined in `database/db.py`. A new `create_user(name, email, password_hash)` function will be added to `database/db.py` — this is a code addition, not a schema change.

## Templates

- **Create:** none
- **Modify:** `templates/register.html` — no structural changes expected; it already posts to `/register` and renders `{{ error }}`. Only touch it if validation requires a new field-level error affordance.

## Files to change

- `app.py` — change `register()` to accept `GET` and `POST`; add validation, call `database/db.py` for user creation, handle duplicate email, redirect on success
- `database/db.py` — add `create_user(name, email, password_hash)` and a `get_user_by_email(email)` helper used for the duplicate-email check

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`generate_password_hash`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic stays in `database/db.py`, never inline in `app.py`
- Use `abort()` for HTTP errors, not bare string returns
- Never hardcode URLs in templates — always use `url_for()`
- Validate: name non-empty, email format, password minimum length (8, per placeholder text), email uniqueness — re-render `register.html` with an `error` message on any failure, do not raise for expected validation failures
- On success, redirect (`redirect`, not render) to `login` via `url_for('login')` — this step does not implement sessions, so the user must log in after registering

## Definition of done

- [ ] Visiting `/register` and submitting valid name/email/password creates a row in `users` with a hashed password (verify via `sqlite3 expense_tracker.db "SELECT * FROM users"`)
- [ ] Submitting with an email that already exists re-renders `register.html` with an error and does not insert a duplicate row
- [ ] Submitting with a missing field or password under 8 characters re-renders `register.html` with an error and does not insert a row
- [ ] Successful registration redirects to `/login`
- [ ] `GET /register` still renders the form unchanged
- [ ] App starts without errors on port 5001 and existing routes (`/`, `/login`, `/terms`, `/privacy`) are unaffected
