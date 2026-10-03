from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from opticamanager.core.session import UserData, UserSession, require_role


def _reset_session() -> None:
    """Reset UserSession singleton state between tests."""
    UserSession._instance = None
    UserSession._user = None


class TestUserSessionSingleton:
    def test_singleton_returns_same_instance(self) -> None:
        """UserSession() always returns the same instance."""
        _reset_session()
        s1 = UserSession()
        s2 = UserSession()
        assert s1 is s2

    def test_singleton_persists_across_calls(self) -> None:
        """State set on one reference is visible on another."""
        _reset_session()
        s1 = UserSession()
        s1._user = UserData(
            id=1,
            username="test",
            name="Test",
            email="t@t.com",
            role_id=1,
            role_name="Admin",
        )
        s2 = UserSession()
        assert s2.is_authenticated is True

    def test_reset_between_tests(self) -> None:
        """_reset_session clears state for test isolation."""
        _reset_session()
        s = UserSession()
        s._user = UserData(
            id=1, username="x", name="X", email="x@x.com", role_id=1, role_name="Admin"
        )
        _reset_session()
        s2 = UserSession()
        assert s2.is_authenticated is False


class TestLogin:
    def test_success(self, mocker: MockerFixture, mock_db_user: MagicMock) -> None:
        """login() returns True with valid credentials."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        result = session.login("admin", "correct_password")

        assert result is True
        assert session.is_authenticated is True
        assert session.current_user is not None
        assert session.current_user.username == "admin"

    def test_failure_wrong_password(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """login() returns False with wrong password."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=False)

        session = UserSession()
        result = session.login("admin", "wrong_password")

        assert result is False
        assert session.is_authenticated is False

    def test_failure_user_not_found(self, mocker: MockerFixture) -> None:
        """login() returns False when username does not exist."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = None
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session

        session = UserSession()
        result = session.login("nonexistent", "any_password")

        assert result is False
        assert session.is_authenticated is False

    def test_login_sets_user_data(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """login() populates current_user with correct UserData."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")

        user = session.current_user
        assert user is not None
        assert user.id == 1
        assert user.username == "admin"
        assert user.name == "Admin User"
        assert user.email == "admin@opticamanager.com"
        assert user.role_id == 1
        assert user.role_name == "Admin"

    def test_login_user_without_role(self, mocker: MockerFixture) -> None:
        """login() handles users without a role gracefully."""
        _reset_session()
        mock_user_no_role = MagicMock()
        mock_user_no_role.id = 2
        mock_user_no_role.username = "no_role_user"
        mock_user_no_role.name = "No Role"
        mock_user_no_role.email = "no@role.com"
        mock_user_no_role.password = "hash"
        mock_user_no_role.role_id = None
        mock_user_no_role.role = None

        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_user_no_role
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        result = session.login("no_role_user", "pass")

        assert result is True
        assert session.current_user is not None
        assert session.current_user.role_name is None

    def test_login_does_not_create_new_user(self, mocker: MockerFixture) -> None:
        """login() does not call session.add for a successful login."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user = MagicMock()
        mock_db_user.id = 1
        mock_db_user.username = "admin"
        mock_db_user.name = "Admin"
        mock_db_user.email = "a@a.com"
        mock_db_user.password = "hash"
        mock_db_user.role_id = 1
        mock_db_user.role = MagicMock()
        mock_db_user.role.name = "Admin"
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")

        mock_session.add.assert_not_called()


class TestLogout:
    def test_logout_clears_user(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """logout() sets current_user to None and is_authenticated to False."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")
        assert session.is_authenticated is True

        session.logout()

        assert session.is_authenticated is False
        assert session.current_user is None

    def test_logout_when_not_logged_in(self) -> None:
        """logout() does not raise when called without prior login."""
        _reset_session()
        session = UserSession()
        session.logout()  # should not raise
        assert session.is_authenticated is False


class TestProperties:
    def test_is_authenticated_false_initially(self) -> None:
        """is_authenticated is False before login."""
        _reset_session()
        session = UserSession()
        assert session.is_authenticated is False

    def test_current_user_none_initially(self) -> None:
        """current_user is None before login."""
        _reset_session()
        session = UserSession()
        assert session.current_user is None

    def test_is_authenticated_after_login(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """is_authenticated is True after successful login."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")
        assert session.is_authenticated is True

    def test_current_user_none_after_logout(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """current_user is None after logout."""
        _reset_session()
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")
        session.logout()
        assert session.current_user is None


class TestHasRole:
    def test_with_matching_role(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """has_role() returns True when current user has the required role."""
        _reset_session()
        mock_db_user.role.name = "Admin"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")
        assert session.has_role("Admin") is True

    def test_without_matching_role(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """has_role() returns False when user has a different role."""
        _reset_session()
        mock_db_user.role.name = "Cajero"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("user", "pass")
        assert session.has_role("Admin") is False

    def test_multiple_roles_any_match(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """has_role() returns True if any of the provided roles match."""
        _reset_session()
        mock_db_user.role.name = "Cajero"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("user", "pass")
        assert session.has_role("Admin", "Cajero") is True

    def test_not_logged_in(self) -> None:
        """has_role() returns False when no user is logged in."""
        _reset_session()
        session = UserSession()
        assert session.has_role("Admin") is False

    def test_user_without_role(self, mocker: MockerFixture) -> None:
        """has_role() returns False when user has no role."""
        _reset_session()
        mock_user_no_role = MagicMock()
        mock_user_no_role.id = 3
        mock_user_no_role.username = "no_role"
        mock_user_no_role.name = "No Role"
        mock_user_no_role.email = "n@n.com"
        mock_user_no_role.password = "hash"
        mock_user_no_role.role_id = None
        mock_user_no_role.role = None

        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_user_no_role
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("no_role", "pass")
        assert session.has_role("Admin") is False
        assert session.has_role("Admin", "Cajero") is False


class TestRequireRole:
    def test_raises_for_wrong_role(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """@require_role raises PermissionError when the role does not match."""
        _reset_session()
        mock_db_user.role.name = "Cajero"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("user", "pass")

        @require_role("Admin")
        def admin_only_action() -> str:
            return "secret_data"

        with pytest.raises(PermissionError, match="Permiso denegado"):
            admin_only_action()

    def test_calls_function_for_correct_role(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """@require_role calls the wrapped function when user has the role."""
        _reset_session()
        mock_db_user.role.name = "Admin"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")

        @require_role("Admin")
        def admin_only_action() -> str:
            return "secret_data"

        result = admin_only_action()
        assert result == "secret_data"

    def test_raises_when_not_logged_in(self) -> None:
        """@require_role raises PermissionError when nobody is logged in."""
        _reset_session()

        @require_role("Admin")
        def protected_action() -> str:
            return "data"

        with pytest.raises(PermissionError, match="Permiso denegado"):
            protected_action()

    def test_multiple_roles_any_suffices(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """@require_role works when user matches any of multiple roles."""
        _reset_session()
        mock_db_user.role.name = "Vendedor"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("vendor", "pass")

        @require_role("Admin", "Vendedor")
        def action() -> str:
            return "data"

        result = action()
        assert result == "data"

    def test_preserves_function_name(
        self, mocker: MockerFixture, mock_db_user: MagicMock
    ) -> None:
        """@require_role preserves the wrapped function's __name__."""
        _reset_session()
        mock_db_user.role.name = "Admin"
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_db_user
        mocker.patch(
            "opticamanager.core.session.SessionManager"
        ).return_value.__enter__.return_value = mock_session
        mocker.patch("opticamanager.core.session.verify_password", return_value=True)

        session = UserSession()
        session.login("admin", "pass")

        @require_role("Admin")
        def my_named_action() -> str:
            return "data"

        assert my_named_action.__name__ == "my_named_action"


class TestUserData:
    def test_dataclass_fields(self) -> None:
        """UserData stores and exposes all fields."""
        data = UserData(
            id=42,
            username="jdoe",
            name="John Doe",
            email="john@example.com",
            role_id=2,
            role_name="Vendedor",
        )
        assert data.id == 42
        assert data.username == "jdoe"
        assert data.name == "John Doe"
        assert data.email == "john@example.com"
        assert data.role_id == 2
        assert data.role_name == "Vendedor"

    def test_dataclass_repr(self) -> None:
        """UserData has a meaningful repr."""
        data = UserData(
            id=1,
            username="admin",
            name="Admin",
            email="a@a.com",
            role_id=1,
            role_name="Admin",
        )
        rep = repr(data)
        assert "UserData" in rep
        assert "admin" in rep

    def test_role_name_can_be_none(self) -> None:
        """UserData accepts None for role_name."""
        data = UserData(
            id=3,
            username="guest",
            name="Guest",
            email="g@g.com",
            role_id=None,
            role_name=None,
        )
        assert data.role_name is None
        assert data.role_id is None
