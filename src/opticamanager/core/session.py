from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.core.security import verify_password
from opticamanager.db import SessionManager
from opticamanager.models.user import User

log = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def require_role(*roles: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Restrict a function to the given roles.

    Raise ``PermissionError`` when the active session holds none of the required
    roles. The decorator used to return ``None`` silently: paired with an outer
    transactional decorator (``@atomic_stock``) that ended in an empty commit
    next to a log line claiming success.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not UserSession().has_role(*roles):
                actual = UserSession().current_user
                raise PermissionError(
                    f"Permiso denegado: se requiere el rol "
                    f"{' o '.join(roles)} y el usuario actual es "
                    f"'{actual.role_name if actual else 'sin sesión'}'"
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


@dataclass
class UserData:
    id: int
    username: str
    name: str
    email: str
    role_id: int | None
    role_name: str | None


class UserSession:
    _instance: UserSession | None = None
    _user: UserData | None = None

    def __new__(cls) -> UserSession:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __setattr__(self, name: str, value: object) -> None:
        # ``_user`` lives at class level. Without this redirect, ``self._user = ...``
        # created an instance attribute that shadowed the class one and ignored
        # direct ``UserSession._user = ...`` assignments from other modules.
        if name == "_user":
            type(self)._user = value  # type: ignore[assignment]
        else:
            super().__setattr__(name, value)

    def login(self, username: str, password: str) -> bool:
        with SessionManager() as session:
            user = session.exec(select(User).where(User.username == username)).first()

            if user is None or not verify_password(password, user.password):
                return False

            assert user.id is not None, "Usuario recién cargado debe tener ID"
            role_name = user.role.name if user.role else None
            self._user = UserData(
                id=user.id,
                username=user.username,
                name=user.name,
                email=user.email,
                role_id=user.role_id,
                role_name=role_name,
            )
            return True

    def logout(self) -> None:
        self._user = None

    @property
    def is_authenticated(self) -> bool:
        return self._user is not None

    @property
    def current_user(self) -> UserData | None:
        return self._user

    def has_role(self, *roles: str) -> bool:
        if self._user is None or self._user.role_name is None:
            return False
        return self._user.role_name in roles

    @staticmethod
    def admin_exists() -> bool:
        """Check if at least one admin user exists in the database."""
        from opticamanager.models.role import Role

        with SessionManager() as session:
            admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
            if admin_role is None:
                return False
            admin_user = session.exec(
                select(User).where(
                    User.role_id == admin_role.id,
                    User.active == True,  # noqa: E712
                )
            ).first()
            return admin_user is not None

    @staticmethod
    def register_admin(
        username: str, name: str, email: str, password: str
    ) -> str | None:
        """Register the first admin user.

        Returns an error message string on failure, or None on success.
        Creates the Admin and Vendedor roles if they don't exist yet.
        """
        from opticamanager.core.security import hash_password
        from opticamanager.models.role import Role

        with SessionManager() as session:
            # ── Ensure roles exist ──
            role_defs = {
                "Admin": "all",
                "Vendedor": "pos",
            }
            for rname, permissions in role_defs.items():
                existing = session.exec(select(Role).where(Role.name == rname)).first()
                if not existing:
                    session.add(Role(name=rname, permissions=permissions))
            session.commit()

            # ── Check if admin already exists ──
            admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
            if admin_role:
                existing_admin = session.exec(
                    select(User).where(
                        User.role_id == admin_role.id,
                        User.active == True,  # noqa: E712
                    )
                ).first()
                if existing_admin:
                    return "Ya existe un administrador registrado"

            # ── Validate uniqueness ──
            existing_user = session.exec(
                select(User).where(User.username == username)
            ).first()
            if existing_user:
                return "El nombre de usuario ya está en uso"

            existing_email = session.exec(
                select(User).where(User.email == email)
            ).first()
            if existing_email:
                return "El correo electrónico ya está registrado"

            # ── Create user ──
            # The Admin role was just ensured above. If it is still missing,
            # abort rather than create a user with no role (role_id NULL).
            if admin_role is None:
                log.error("Cannot register admin: the Admin role could not be created")
                return "No se pudo crear el rol Admin para el administrador"

            user = User(
                username=username,
                name=name,
                email=email,
                password=hash_password(password),
                role_id=admin_role.id,
                active=True,
            )
            session.add(user)
            session.commit()
            return None  # Success
