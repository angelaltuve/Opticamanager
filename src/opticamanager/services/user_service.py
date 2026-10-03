from __future__ import annotations

from sqlalchemy.orm import selectinload
from sqlmodel import Session, func, select

from opticamanager.core.logging_config import get_logger
from opticamanager.core.security import hash_password
from opticamanager.db import SessionManager
from opticamanager.models import Role, User

log = get_logger(__name__)

# ── Read ──


def list_users() -> list[User]:
    """Return all users with their associated role loaded."""
    with SessionManager() as session:
        # selectinload avoids the N+1 that "for u in users: _ = u.role" causes
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .order_by(User.created_at.desc())
        )
        return list(session.exec(stmt).all())


def get_user(user_id: int) -> User | None:
    """Return a single user by id."""
    with SessionManager() as session:
        return session.get(User, user_id)


def count_admins() -> int:
    """Return the number of active Admin users."""
    with SessionManager() as session:
        admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
        if not admin_role:
            return 0
        return len(
            session.exec(
                select(User).where(
                    User.role_id == admin_role.id,
                    User.active == True,  # noqa: E712
                )
            ).all()
        )


def list_roles() -> list[Role]:
    """Return all roles (for combo boxes)."""
    with SessionManager() as session:
        return list(session.exec(select(Role).order_by(Role.name)).all())


# ── Create ──


def create_user(
    username: str,
    name: str,
    email: str,
    password: str,
    role_id: int | None,
    active: bool = True,
) -> str | None:
    """Create a new user.

    Returns an error message on failure, or None on success.
    """
    with SessionManager() as session:
        # ── Uniqueness checks ──
        existing_user = session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing_user:
            return "El nombre de usuario ya está en uso"

        existing_email = session.exec(select(User).where(User.email == email)).first()
        if existing_email:
            return "El correo electrónico ya está registrado"

        # ── Validate role exists ──
        if role_id is not None:
            role = session.get(Role, role_id)
            if not role:
                return "El rol seleccionado no existe"

        user = User(
            username=username,
            name=name,
            email=email,
            password=hash_password(password),
            role_id=role_id,
            active=active,
        )
        session.add(user)
        session.commit()
        log.info("Created user: %s (role_id=%s)", username, role_id)
        return None


# ── Update ──


def update_user(
    user_id: int,
    name: str,
    email: str,
    role_id: int | None,
    active: bool,
) -> str | None:
    """Update an existing user's profile fields.

    Returns an error message on failure, or None on success.
    Does *not* change the password; use change_password() for that.
    """
    with SessionManager() as session:
        user = session.get(User, user_id)
        if not user:
            return "Usuario no encontrado"

        # ── Email uniqueness (exclude self) ──
        existing = session.exec(
            select(User).where(User.email == email, User.id != user_id)
        ).first()
        if existing:
            return "El correo electrónico ya está registrado por otro usuario"

        # ── Prevent removing last admin ──
        if role_id is not None:
            new_role = session.get(Role, role_id)
            if new_role and new_role.name != "Admin":
                # Check if user is the last active admin
                admin_role = session.exec(
                    select(Role).where(Role.name == "Admin")
                ).first()
                if admin_role and user.role_id == admin_role.id and user.active:
                    admin_count = count_admins()
                    if admin_count <= 1:
                        return (
                            "No puedes cambiar el rol del último administrador activo"
                        )

        # ── Prevent deactivating the last active admin ──
        if not active and user.active:
            admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
            if admin_role and user.role_id == admin_role.id:
                admin_count = count_admins()
                if admin_count <= 1:
                    return "No puedes desactivar al último administrador activo"

        user.name = name
        user.email = email
        user.role_id = role_id
        user.active = active
        session.add(user)
        session.commit()
        log.info("Updated user: id=%s", user_id)
        return None


# ── Delete ──


def _dependientes_de_usuario(session: Session, user: User) -> list[tuple[str, int]]:
    """Return the (label, count) pairs of rows that block deleting ``user``.

    Sales, cash sessions and inventory logs all carry a NOT NULL foreign key to
    ``users.id``, so the ORM would try to null them out and the database would
    reject the statement. Detecting them up front turns an unhandled
    ``IntegrityError`` into a message the UI can show.
    """
    from opticamanager.models.cash_session import CashSession
    from opticamanager.models.inventory_log import InventoryLog
    from opticamanager.models.sale import Sale

    assert user.id is not None, "El usuario debe estar persistido para contarlo"
    conteos = [
        (
            "ventas",
            session.exec(select(func.count()).where(Sale.user_id == user.id)).one(),
        ),
        (
            "cajas",
            session.exec(
                select(func.count()).where(CashSession.user_id == user.id)
            ).one(),
        ),
        (
            "movimientos de inventario",
            session.exec(
                select(func.count()).where(InventoryLog.user_id == user.id)
            ).one(),
        ),
    ]
    return [(nombre, int(cantidad)) for nombre, cantidad in conteos if cantidad]


def delete_user(user_id: int) -> str | None:
    """Delete a user.

    Returns an error message on failure, or None on success.
    """
    with SessionManager() as session:
        user = session.get(User, user_id)
        if not user:
            return "Usuario no encontrado"

        # ── Prevent deleting the last active admin ──
        admin_role = session.exec(select(Role).where(Role.name == "Admin")).first()
        if admin_role and user.role_id == admin_role.id and user.active:
            admin_count = count_admins()
            if admin_count <= 1:
                return "No puedes eliminar al último administrador activo"

        # ── Block deletion when dependent rows still reference the user ──
        # Sales, cash sessions and inventory hold NOT NULL FKs. Deleting them
        # here raised an IntegrityError that escaped the Qt slot instead of
        # reaching the user.
        blockers = _dependientes_de_usuario(session, user)
        if blockers:
            detalle = ", ".join(f"{n} ({c})" for n, c in blockers)
            return (
                "No se puede eliminar el usuario porque tiene registros "
                f"asociados: {detalle}. Reasigna o elimina esos registros primero."
            )

        session.delete(user)
        session.commit()
        log.info("Deleted user: id=%s", user_id)
        return None


# ── Password ──


def change_password(user_id: int, new_password: str) -> str | None:
    """Change a user's password.

    Returns an error message on failure, or None on success.
    """
    if len(new_password) < 8:
        return "La contraseña debe tener al menos 8 caracteres"

    with SessionManager() as session:
        user = session.get(User, user_id)
        if not user:
            return "Usuario no encontrado"
        user.password = hash_password(new_password)
        session.add(user)
        session.commit()
        log.info("Changed password for user: id=%s", user_id)
        return None
