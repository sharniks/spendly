# Spec: Login and Logout

## Overview
This feature implements session-based authentication for Spendly: a working `POST /login` that verifies a user's email and password against the `users` table and starts a session, and a working `GET /logout` that ends it. Registration (Step 2) created accounts but left users to authenticate manually afterward — this step closes that gap by giving the app its first real notion of "who is currently signed in," which every later step (profile, expense CRUD) will depend on to identify the current user.

## Depends on
- Step 1 — Database setup (`database/db.py`: `get_db()`, `users` table with `password_hash`) — complete
- Step 2 — Registration (`users` table populated, `get_user_by_email()` helper, werkzeug password-hashing pattern, `app.py` GET/POST route-splitting pattern) — complete

## Routes
- `GET /login` — renders the sign-in form; already implemented, unchanged — public
- `POST /login` — validates email + password against `users`, starts a session on success, re-renders `login.html` with `error` on failure — public
- `GET /logout` — clears the session and redirects to `login` — logged-in (safe no-op if no session exists)

## Database changes
No database changes. `database/db.py` already has `get_db()`, `init_db()`, `seed_db()`, `get_user_by_email()`, and `create_user()` — all reusable as-is. No new tables, columns, or helper functions are needed for this step; `get_user_by_email()` is sufficient to fetch the stored `password_hash` for verification.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — change the form's `action="/login"` to `action="{{ url_for('login') }}"` (matches the "never hardcode URLs" rule); no structural change needed otherwise, since it already renders both `{{ error }}` and `{{ success }}` blocks
  - `templates/base.html` — make the navbar session-aware: when `session.user_id` is set, show a "Logout" link (`url_for('logout')`) in place of "Sign in" / "Get started"

## Files to change
- `app.py` — import `session` from `flask` and `check_password_hash` from `werkzeug.security`; set `app.secret_key`; add `POST` handling to `/login`; implement `/logout`
- `templates/login.html` — fix hardcoded form action
- `templates/base.html` — conditional nav links based on session state

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`check_password_hash` against the stored `password_hash`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic stays in `database/db.py` — the login route only calls `get_user_by_email()`, it does not query the database directly
- Mirror the existing `register()` validation pattern: on failure, re-render `login.html` with `error=`; never return raw strings
- `/logout` must render/redirect properly — no bare string return, per CLAUDE.md's explicit warning
- `app.secret_key` must be set for Flask sessions to work; use a hardcoded development value and note in a comment that it must move to an environment variable before production use
- Do not implement `/profile` or any other stub route — out of scope for this step

## Definition of done
- [ ] Visiting `/login` and submitting valid credentials (e.g. `demo@spendly.com` / `demo123`) redirects successfully and a session cookie is set
- [ ] Submitting an unknown email re-renders `login.html` with an error message, not a 500 or raw string
- [ ] Submitting a known email with the wrong password re-renders `login.html` with an error message
- [ ] After logging in, visiting `/logout` clears the session and redirects to `/login`
- [ ] Visiting `/logout` while not logged in does not error (safe no-op redirect)
- [ ] The navbar in `base.html` shows "Logout" instead of "Sign in" / "Get started" when a session is active, and reverts after logout
- [ ] No hardcoded URLs remain in `login.html` (`url_for()` used throughout)
- [ ] `pytest` passes with no regressions to existing registration/landing tests
