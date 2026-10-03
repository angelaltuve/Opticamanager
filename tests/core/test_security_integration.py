"""Security integration tests against the real (isolated) test database.

Covers:
- Passwords are never stored in plaintext (bcrypt hash in the DB).
- SQL injection attempts on login and user registration never execute
  arbitrary SQL and never authenticate.

These tests use the ephemeral per-process DB configured in tests/conftest.py.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from opticamanager.core.security import verify_password
from opticamanager.core.session import UserSession
from opticamanager.db import SessionManager
from opticamanager.models import User
from opticamanager.services.user_service import change_password, create_user

# Unique usernames owned by this module (cleaned up in teardown_module).
_OWN_USERNAMES = [
    "sec_crud_user",
    "sec_admin_hash",
    "sec_literal_inject",
    "sec_or_login",
]


def _reset_session() -> None:
    """Reset the UserSession singleton between tests."""
    UserSession._instance = None
    UserSession._user = None


def _delete_by_username(username: str) -> None:
    with SessionManager() as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user:
            session.delete(user)
            session.commit()


def setup_module() -> None:
    _reset_session()


def teardown_module() -> None:
    for username in _OWN_USERNAMES:
        _delete_by_username(username)
    _reset_session()


def _create_clean_user(
    username: str, name: str, email: str, password: str
) -> str | None:
    """Delete leftovers from a previous run, then create the user fresh."""
    _delete_by_username(username)
    return create_user(
        username=username,
        name=name,
        email=email,
        password=password,
        role_id=None,
        active=True,
    )


# ── Passwords never stored in plaintext ─────────────────────────────────────


class TestPasswordNuncaEnClaro:
    def test_create_user_guarda_hash_bcrypt_no_plaintext(self) -> None:
        password = "ClaveSecreta#123"
        error = create_user(
            username="sec_crud_user",
            name="Sec User",
            email="sec.user@test.com",
            password=password,
            role_id=None,
            active=True,
        )
        assert error is None

        with SessionManager() as session:
            user = session.exec(
                select(User).where(User.username == "sec_crud_user")
            ).first()
            assert user is not None
            # Never stored in plaintext
            assert user.password != password
            assert password not in user.password
            assert user.password.startswith("$2b$")
            # And the stored hash is a valid bcrypt hash of the password
            assert verify_password(password, user.password)

    def test_register_admin_guarda_hash_bcrypt_no_plaintext(self) -> None:
        if UserSession.admin_exists():
            pytest.skip("Ya existe un admin en la BD de test; flujo feliz no aplicable")

        password = "AdminClave#78"
        error = UserSession.register_admin(
            username="sec_admin_hash",
            name="Sec Admin",
            email="sec.admin@test.com",
            password=password,
        )
        assert error is None

        with SessionManager() as session:
            user = session.exec(
                select(User).where(User.username == "sec_admin_hash")
            ).first()
            assert user is not None
            assert user.password != password
            assert password not in user.password
            assert user.password.startswith("$2b$")
            assert verify_password(password, user.password)

    def test_change_password_guarda_nuevo_hash(self) -> None:
        error = _create_clean_user(
            "sec_crud_user", "Sec User", "sec.user@test.com", "ClaveSecreta#123"
        )
        assert error is None

        with SessionManager() as session:
            user = session.exec(
                select(User).where(User.username == "sec_crud_user")
            ).first()
            assert user is not None
            user_id = user.id
            assert user_id is not None
            old_hash = user.password

        new_password = "NuevaClave#456"
        change_error = change_password(user_id, new_password)
        assert change_error is None

        with SessionManager() as session:
            user = session.get(User, user_id)
            assert user is not None
            assert user.password != new_password
            assert new_password not in user.password
            assert user.password.startswith("$2b$")
            # The new hash verifies and differs from the old one (new salt)
            assert verify_password(new_password, user.password)
            assert user.password != old_hash

    def test_salting_genera_hashes_distintos(self) -> None:
        """Two users with the same password get different hashes (per-call salt)."""
        password = "MismaClave#999"
        error = _create_clean_user(
            "sec_crud_user", "Sec User", "sec.user@test.com", password
        )
        assert error is None
        error = _create_clean_user(
            "sec_or_login", "Sec Or Login", "sec.or.login@test.com", password
        )
        assert error is None

        with SessionManager() as session:
            users = session.exec(
                select(User).where(User.username.in_(["sec_crud_user", "sec_or_login"]))
            ).all()
            hashes = {u.password for u in users}
            assert len(hashes) == 2


# ── SQL injection attempts ──────────────────────────────────────────────────


class TestSQLInjection:
    def test_login_or_1_es_1_no_autentica(self) -> None:
        _reset_session()
        session = UserSession()

        # Classic authentication bypass
        assert session.login("' OR '1'='1' --", "cualquier") is False
        assert session.is_authenticated is False

        # Variant closing the value and commenting the rest
        assert session.login("admin' --", "x") is False
        assert session.is_authenticated is False

    def test_login_drop_table_no_destruye_la_bd(self) -> None:
        _reset_session()
        session = UserSession()

        before = None
        with SessionManager() as db:
            before = len(db.exec(select(User)).all())

        assert session.login("'; DROP TABLE users; --", "x") is False
        assert session.is_authenticated is False

        # Table still exists and still has the same rows
        with SessionManager() as db:
            after = len(db.exec(select(User)).all())
        assert after == before

    def test_login_password_inyectada_no_autentica(self) -> None:
        """A real user with an injected password must not authenticate."""
        error = _create_clean_user(
            "sec_crud_user", "Sec User", "sec.user@test.com", "ClaveSecreta#123"
        )
        assert error is None

        _reset_session()
        assert UserSession().login("sec_crud_user", "' OR '1'='1' --") is False
        assert UserSession().is_authenticated is False

    def test_create_user_username_inyectado_tratado_como_literal(self) -> None:
        """Embedded quotes are parameterized, never executed as SQL."""
        before = None
        with SessionManager() as db:
            before = len(db.exec(select(User)).all())

        payload = "sec_literal_inject'); DROP TABLE users; --"
        error = create_user(
            username=payload,
            name="Injected",
            email="sec.literal@test.com",
            password="ClaveSegura#7",
            role_id=None,
            active=True,
        )
        # Either the literal username is created (parameterized) or a
        # uniqueness error is returned; never arbitrary SQL execution.
        assert error is None or "en uso" in error

        with SessionManager() as db:
            users = db.exec(select(User)).all()
            assert len(users) >= before
            if error is None:
                literal = db.exec(select(User).where(User.username == payload)).first()
                assert literal is not None

    def test_create_user_email_inyectado_no_ejecuta_sql(self) -> None:
        """Malformed emails with quotes are stored as literals / rejected."""
        before = None
        with SessionManager() as db:
            before = len(db.exec(select(User)).all())

        email_payload = "sec@test.com'); DELETE FROM users; --"
        error = create_user(
            username="sec_email_inject_ok",
            name="Email Injected",
            email=email_payload,
            password="ClaveSegura#8",
            role_id=None,
            active=True,
        )
        assert error is None or "registrado" in error

        with SessionManager() as db:
            users = db.exec(select(User)).all()
            assert len(users) >= before

        _delete_by_username("sec_email_inject_ok")

    def test_register_admin_username_inyectado_no_crea_admin(self) -> None:
        """register_admin never creates a user from injected SQL fragments."""
        payload = "sec_admin' OR '1'='1' --"
        error = UserSession.register_admin(
            username=payload,
            name="Injected Admin",
            email="sec.injected.admin@test.com",
            password="ClaveSegura#9",
        )
        # Either rejected (admin already exists / literal in use) or the
        # literal username is created; never a bypass admin.
        with SessionManager() as db:
            created = db.exec(
                select(User).where(
                    User.username.in_(["sec_admin' OR '1'='1' --", "admin", "1"])
                )
            ).all()
        if error is None:
            assert any(u.username == payload for u in created)
            _delete_by_username(payload)
        else:
            assert "administrador" in error or "en uso" in error
