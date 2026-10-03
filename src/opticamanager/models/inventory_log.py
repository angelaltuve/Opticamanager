from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .product import Product
    from .user import User


class InventoryLog(AuditBase, table=True):
    __tablename__ = "inventory_logs"

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id")
    quantity: int = Field()
    unit_cost: Decimal | None = Field(default=None, sa_type=Numeric(10, 2))
    reason: str = Field(max_length=255)
    user_id: int = Field(foreign_key="users.id")

    product: Mapped[Optional["Product"]] = Relationship(back_populates="inventory_logs")
    user: Mapped[Optional["User"]] = Relationship(back_populates="inventory_logs")


from .product import Product  # noqa: E402
from .user import User  # noqa: E402
