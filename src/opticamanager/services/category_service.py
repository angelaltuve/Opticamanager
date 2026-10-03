from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager

if TYPE_CHECKING:
    from opticamanager.models.category import Category

log = get_logger(__name__)

_MAX_NAME_LENGTH: int = 100
_MAX_DESC_LENGTH: int = 255


def _validate_name(name: str) -> str:
    """Validate and normalize a category name."""
    stripped = name.strip()
    if not stripped:
        raise ValueError("El nombre de la categoría es obligatorio")
    if len(stripped) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"El nombre no puede tener más de {_MAX_NAME_LENGTH} caracteres"
        )
    return stripped


def _validate_description(description: str | None) -> str | None:
    """Validate and normalize a category description."""
    if description is None:
        return None
    stripped = description.strip()
    if stripped and len(stripped) > _MAX_DESC_LENGTH:
        raise ValueError(
            f"La descripción no puede tener más de {_MAX_DESC_LENGTH} caracteres"
        )
    return stripped or None


def _check_duplicate_name(name: str, exclude_id: int | None = None) -> None:
    """Raise ValueError if a category with the same name already exists."""
    from opticamanager.models.category import Category

    with SessionManager() as session:
        stmt = select(Category).where(Category.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        existing = session.exec(stmt).first()
    if existing:
        raise ValueError(f"Ya existe una categoría con el nombre '{name}'")


def list_categories() -> list[Category]:
    from opticamanager.models.category import Category

    with SessionManager() as session:
        cats = session.exec(select(Category).order_by(Category.name)).all()
    return list(cats)


def get_category(category_id: int) -> Category | None:
    from opticamanager.models.category import Category

    with SessionManager() as session:
        return session.get(Category, category_id)


def create_category(name: str, description: str | None = None) -> Category:
    from opticamanager.models.category import Category

    name = _validate_name(name)
    description = _validate_description(description)
    _check_duplicate_name(name)
    with SessionManager() as session:
        cat = Category(name=name, description=description)
        session.add(cat)
        session.commit()
        session.refresh(cat)
    log.info("categoria_creada: id=%d name=%s", cat.id, cat.name)
    return cat


def update_category(
    category_id: int, name: str, description: str | None = None
) -> Category:
    from opticamanager.models.category import Category

    name = _validate_name(name)
    description = _validate_description(description)
    _check_duplicate_name(name, exclude_id=category_id)
    with SessionManager() as session:
        cat = session.get(Category, category_id)
        if not cat:
            raise ValueError(f"Categoría ID {category_id} no encontrada")
        cat.name = name
        cat.description = description if description else None
        session.add(cat)
        session.commit()
        session.refresh(cat)
    log.info("categoria_actualizada: id=%d name=%s", cat.id, cat.name)
    return cat


def delete_category(category_id: int) -> bool:
    from opticamanager.models.category import Category

    with SessionManager() as session:
        cat = session.get(Category, category_id)
        if not cat:
            return False
        session.delete(cat)
        session.commit()
    log.info("categoria_eliminada: id=%d", category_id)
    return True


__all__ = [
    "list_categories",
    "get_category",
    "create_category",
    "update_category",
    "delete_category",
]
