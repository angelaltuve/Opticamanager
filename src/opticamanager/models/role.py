from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .user import User


class Role(AuditBase, table=True):
    __tablename__ = "roles"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=50)
    permissions: str | None = None

    users: Mapped[list["User"]] = Relationship(back_populates="role")
