from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .product import Product
    from .sale import Sale


class SaleDetail(AuditBase, table=True):
    __tablename__ = "sale_details"

    id: int | None = Field(default=None, primary_key=True)
    sale_id: int = Field(foreign_key="sales.id")
    product_id: int = Field(foreign_key="products.id")
    quantity: int = Field()
    unit_price: Decimal = Field(sa_type=Numeric(10, 2))
    subtotal: Decimal = Field(sa_type=Numeric(10, 2))

    sale: Mapped[Optional["Sale"]] = Relationship(back_populates="details")
    product: Mapped[Optional["Product"]] = Relationship(back_populates="sale_details")


from .product import Product  # noqa: E402
from .sale import Sale  # noqa: E402
