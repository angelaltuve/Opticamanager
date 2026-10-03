from __future__ import annotations

import os
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

# ── Headless Qt guard ─────────────────────────────────────────────────────────
# The user profile may export QT_QPA_PLATFORMTHEME=gtk3, which makes QApplication
# abort silently when no DISPLAY/WAYLAND is available (no traceback, pytest dies
# mid-run). Drop it before any Qt/opticamanager import so the suite runs headless
# regardless of the calling environment.
os.environ.pop("QT_QPA_PLATFORMTHEME", None)

# ── Test DB isolation ─────────────────────────────────────────────────────────
# The app builds its SQLite engine at import time (db/database.py). To keep the
# test suite away from the real database (data/opticamanager.db), point it at a
# throwaway per-process DB BEFORE any opticamanager module is imported below.
_TEST_DB_ROOT = Path(__file__).resolve().parent.parent / "data" / "_test"
_TEST_DB_ROOT.mkdir(parents=True, exist_ok=True)

# Sweep leftovers from crashed runs (older than 1 day, other pids untouched).
_now = time.time()
for _stale_dir in _TEST_DB_ROOT.glob("pid-*"):
    try:
        if _now - _stale_dir.stat().st_mtime > 86_400:
            for _f in _stale_dir.glob("*"):
                _f.unlink()
            _stale_dir.rmdir()
    except OSError:
        pass

_TEST_DB_DIR = _TEST_DB_ROOT / f"pid-{os.getpid()}"
_TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
os.environ["OPTICAMANAGER_DB_PATH"] = str(_TEST_DB_DIR / "opticamanager.db")

# The engine created below now targets the ephemeral test DB.
from opticamanager.db import create_db_and_tables  # noqa: E402
from opticamanager.models.user import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_db() -> Generator[None, None, None]:
    """Create the schema on the ephemeral test DB and clean it up afterwards."""
    create_db_and_tables()
    yield
    for f in list(_TEST_DB_DIR.glob("*")):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        _TEST_DB_DIR.rmdir()
    except OSError:
        pass


@pytest.fixture
def mock_db_user(mocker: MockerFixture) -> MagicMock:
    """Create a mock User with Role for session tests."""
    mock_role = MagicMock()
    mock_role.name = "Admin"

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.username = "admin"
    mock_user.name = "Admin User"
    mock_user.email = "admin@opticamanager.com"
    mock_user.password = "$2b$12$hashedpassword1234567890abcde"
    mock_user.role_id = 1
    mock_user.role = mock_role

    return mock_user


@pytest.fixture
def mock_session_manager(mocker: MockerFixture) -> Generator[MagicMock, None, None]:
    """Mock SessionManager to return a controlled session."""
    mock_session = MagicMock()
    mock_session_manager = mocker.patch("opticamanager.core.session.SessionManager")
    mock_session_manager.return_value.__enter__.return_value = mock_session
    yield mock_session
