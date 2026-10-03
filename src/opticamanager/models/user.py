from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .cash_session import CashSession
    from .inventory_log import InventoryLog
    from .role import Role
    from .sale import Sale


class User(AuditBase, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, max_length=50)
    name: str = Field(max_length=100)
    email: str = Field(unique=True, max_length=100)
    password: str = Field(max_length=255)
    role_id: int | None = Field(default=None, foreign_key="roles.id")
    active: bool = Field(default=True)

    role: Mapped[Optional["Role"]] = Relationship(back_populates="users")
    sales: Mapped[list["Sale"]] = Relationship(back_populates="user")
    inventory_logs: Mapped[list["InventoryLog"]] = Relationship(back_populates="user")
    cash_sessions: Mapped[list["CashSession"]] = Relationship(back_populates="user")


from .cash_session import CashSession  # noqa: E402
from .inventory_log import InventoryLog  # noqa: E402
from .role import Role  # noqa: E402
