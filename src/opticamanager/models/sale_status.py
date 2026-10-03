from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .sale import Sale


class SaleStatus(AuditBase, table=True):
    __tablename__ = "sale_statuses"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=50)

    sales: Mapped[list["Sale"]] = Relationship(back_populates="status")
