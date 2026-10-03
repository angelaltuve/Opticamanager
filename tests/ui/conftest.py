from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from opticamanager.core.session import UserSession


def _reset_session() -> None:
    """Reset UserSession singleton between tests."""
    UserSession._instance = None
    UserSession._user = None


@pytest.fixture(autouse=True)
def reset_user_session() -> None:
    """Every UI test starts with a clean UserSession."""
    _reset_session()


@pytest.fixture
def mock_session_data(mocker: MockerFixture) -> MagicMock:
    """Create a mock user and authenticate UserSession.

    Returns the mock user object for assertions.
    """
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.username = "admin"
    mock_user.name = "Admin User"
    mock_user.email = "admin@test.com"
    mock_user.role_id = 1
    mock_user.role.name = "Admin"

    # Mock UserSession.login to succeed
    mocker.patch.object(UserSession, "login", return_value=True)
    UserSession._user = mock_user

    return mock_user
