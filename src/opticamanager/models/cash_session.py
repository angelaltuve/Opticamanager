from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .user import User


class CashSession(AuditBase, table=True):
    __tablename__ = "cash_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    opened_at: datetime = Field(default_factory=datetime.now)
    closed_at: datetime | None = Field(default=None)
    initial_balance: Decimal = Field(sa_type=Numeric(10, 2))
    final_balance: Decimal | None = Field(default=None, sa_type=Numeric(10, 2))
    notes: str | None = None

    user: Mapped[Optional["User"]] = Relationship(back_populates="cash_sessions")


from .user import User  # noqa: E402
