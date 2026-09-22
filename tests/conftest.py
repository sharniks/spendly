"""Shared pytest fixtures for Spendly.

Every test runs against an isolated, throwaway SQLite file. The real
``expense_tracker.db`` at the project root is never opened: ``DB_PATH`` is
redirected *before* ``app`` is imported (``app.py`` calls ``init_db()`` and
``seed_db()`` at import time), and again per test via ``monkeypatch``.
"""

import importlib
import os
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database.db as db_module  # noqa: E402

# Guard for the first import of app.py (import-time init_db/seed_db).
_IMPORT_GUARD_DIR = tempfile.mkdtemp(prefix="spendly-import-")
db_module.DB_PATH = os.path.join(_IMPORT_GUARD_DIR, "import_guard.db")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test_expense_tracker.db")
    monkeypatch.setattr(db_module, "DB_PATH", path)
    db_module.init_db()
    return path


@pytest.fixture
def app_module(db_path):
    return importlib.import_module("app")


@pytest.fixture
def app(app_module):
    flask_app = app_module.app
    flask_app.config.update(TESTING=True)
    return flask_app
