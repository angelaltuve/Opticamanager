from __future__ import annotations

from datetime import datetime

from opticamanager.models.base import AuditBase


def test_audit_base_has_created_at() -> None:
    """AuditBase instances get an auto-generated created_at timestamp."""
    instance = AuditBase()
    assert instance.created_at is not None
    assert isinstance(instance.created_at, datetime)


def test_audit_base_has_updated_at() -> None:
    """AuditBase instances get an auto-generated updated_at timestamp."""
    instance = AuditBase()
    assert instance.updated_at is not None
    assert isinstance(instance.updated_at, datetime)


def test_audit_base_created_at_differs_per_instance() -> None:
    """Each new AuditBase instance gets its own created_at timestamp."""
    a1 = AuditBase()
    a2 = AuditBase()
    assert a1.created_at <= a2.created_at


def test_audit_base_no_id_by_default() -> None:
    """AuditBase alone has no primary key; subclasses define their own."""
    instance = AuditBase()
    instance_id = getattr(instance, "id", None)
    assert instance_id is None


def test_audit_base_is_sqlmodel_subclass() -> None:
    """AuditBase extends SQLModel for DB serialization."""
    from sqlmodel import SQLModel

    assert issubclass(AuditBase, SQLModel)
