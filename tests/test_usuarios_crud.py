from __future__ import annotations

from sqlmodel import select

from opticamanager.core.security import verify_password
from opticamanager.db import SessionManager
from opticamanager.models import Role, User
from opticamanager.services.user_service import (
    change_password,
    count_admins,
    create_user,
    delete_user,
    get_user,
    list_roles,
    list_users,
    update_user,
)

_TEST_ADMIN_ID: int | None = None
_TEST_USER_ID: int | None = None


def setup_module() -> None:
    """Create test data: Admin role + admin user + regular user."""
    global _TEST_ADMIN_ID, _TEST_USER_ID
    with SessionManager() as session:
        # Ensure Admin role
        role = session.exec(select(Role).where(Role.name == "Admin")).first()
        if not role:
            role = Role(name="Admin")
            session.add(role)
            session.commit()

        # Create admin test user
        admin = session.exec(
            select(User).where(User.username == "test_admin_crud")
        ).first()
        if not admin:
            admin = User(
                username="test_admin_crud",
                name="Admin Test",
                email="admin@crud.test",
                password="x",
                role_id=role.id,
                active=True,
            )
            session.add(admin)
            session.commit()
        _TEST_ADMIN_ID = admin.id

        # Create a regular test user
        user = session.exec(
            select(User).where(User.username == "test_user_crud")
        ).first()
        if not user:
            user = User(
                username="test_user_crud",
                name="User Test",
                email="user@crud.test",
                password="x",
                role_id=role.id,
                active=True,
            )
            session.add(user)
            session.commit()
        _TEST_USER_ID = user.id


def teardown_module() -> None:
    """Clean up test users."""
    with SessionManager() as session:
        for uname in ["test_new_user", "test_user_crud", "test_admin_crud"]:
            u = session.exec(select(User).where(User.username == uname)).first()
            if u:
                session.delete(u)
        session.commit()


# ── list_users / get_user ──


def test_list_users() -> None:
    users = list_users()
    assert len(users) >= 2
    usernames = {u.username for u in users}
    assert "test_admin_crud" in usernames
    assert "test_user_crud" in usernames


def test_get_user_found() -> None:
    assert _TEST_ADMIN_ID is not None
    user = get_user(_TEST_ADMIN_ID)
    assert user is not None
    assert user.username == "test_admin_crud"


def test_get_user_not_found() -> None:
    assert get_user(99999) is None


# ── list_roles ──


def test_list_roles() -> None:
    roles = list_roles()
    names = {r.name for r in roles}
    assert "Admin" in names


# ── count_admins ──


def test_count_admins() -> None:
    assert count_admins() >= 1


# ── create_user ──


def test_create_user_success() -> None:
    error = create_user(
        username="test_new_user",
        name="New User",
        email="new@crud.test",
        password="secret1234",
        role_id=None,
        active=True,
    )
    assert error is None

    # Verify
    with SessionManager() as session:
        u = session.exec(select(User).where(User.username == "test_new_user")).first()
        assert u is not None
        assert u.name == "New User"
        assert u.email == "new@crud.test"
        assert verify_password("secret1234", u.password)
        assert u.active is True


def test_create_user_duplicate_username() -> None:
    error = create_user(
        username="test_admin_crud",
        name="Dup",
        email="dup@crud.test",
        password="secret1234",
        role_id=None,
    )
    assert error is not None
    assert "ya está en uso" in error


def test_create_user_duplicate_email() -> None:
    error = create_user(
        username="unique_user",
        name="Dup Email",
        email="admin@crud.test",
        password="secret1234",
        role_id=None,
    )
    assert error is not None
    assert "ya está registrado" in error


# ── update_user ──


def test_update_user_success() -> None:
    assert _TEST_USER_ID is not None
    error = update_user(
        _TEST_USER_ID,
        name="Updated Name",
        email="updated@crud.test",
        role_id=None,
        active=True,
    )
    assert error is None

    user = get_user(_TEST_USER_ID)
    assert user is not None
    assert user.name == "Updated Name"
    assert user.email == "updated@crud.test"


def test_update_user_not_found() -> None:
    error = update_user(
        99999,
        name="Nobody",
        email="nobody@crud.test",
        role_id=None,
        active=True,
    )
    assert error is not None
    assert "no encontrado" in error


def test_update_user_duplicate_email() -> None:
    assert _TEST_ADMIN_ID is not None
    error = update_user(
        _TEST_ADMIN_ID,
        name="Admin Test",
        email="updated@crud.test",  # Already taken by test_user_crud
        role_id=None,
        active=True,
    )
    assert error is not None
    assert "ya está registrado" in error


def test_update_last_admin_role_change_protected() -> None:
    """Cannot change the role of the last active admin."""
    with SessionManager() as session:
        admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
        assert admin_role is not None
        non_admin_role = Role(name="TempTestRole")
        session.add(non_admin_role)
        session.flush()
        non_admin_role_id = non_admin_role.id

        # Get last admin
        admins = session.exec(
            select(User).where(
                User.role_id == admin_role.id,
                User.active == True,  # noqa: E712
            )
        ).all()
        if len(admins) == 1:
            last_admin = admins[0]
            assert last_admin.id is not None
            error = update_user(
                last_admin.id,
                name=last_admin.name,
                email=last_admin.email,
                role_id=non_admin_role_id,
                active=True,
            )
            assert error is not None
            assert "último administrador" in error or "no puedes" in error.lower()

        # Cleanup temp role
        session.delete(non_admin_role)
        session.commit()


# ── change_password ──


def test_change_password_success() -> None:
    assert _TEST_USER_ID is not None
    error = change_password(_TEST_USER_ID, "newpass1234")
    assert error is None

    with SessionManager() as session:
        u = session.get(User, _TEST_USER_ID)
        assert u is not None
        assert verify_password("newpass1234", u.password)


def test_change_password_too_short() -> None:
    assert _TEST_USER_ID is not None
    error = change_password(_TEST_USER_ID, "short")
    assert error is not None
    assert "8" in error or "caracteres" in error


def test_change_password_user_not_found() -> None:
    error = change_password(99999, "newpass1234")
    assert error is not None
    assert "no encontrado" in error


# ── delete_user ──


def test_delete_user_not_found() -> None:
    error = delete_user(99999)
    assert error is not None
    assert "no encontrado" in error


def test_delete_last_admin_protected() -> None:
    with SessionManager() as session:
        admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
        assert admin_role is not None
        admins = session.exec(
            select(User).where(
                User.role_id == admin_role.id,
                User.active == True,  # noqa: E712
            )
        ).all()
        if len(admins) == 1:
            assert admins[0].id is not None
            error = delete_user(admins[0].id)
            assert error is not None
            assert "último administrador" in error
