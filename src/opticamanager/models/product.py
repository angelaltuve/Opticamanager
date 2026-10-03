from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .category import Category
    from .inventory_log import InventoryLog
    from .sale_detail import SaleDetail


class Product(AuditBase, table=True):
    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=150)
    barcode: str | None = Field(default=None, unique=True, max_length=50)
    category_id: int | None = Field(default=None, foreign_key="categories.id")
    description: str | None = None
    cost_price_usd: Decimal = Field(sa_type=Numeric(10, 2))
    sale_price_usd: Decimal = Field(sa_type=Numeric(10, 2))
    stock_quantity: int = Field(default=0)
    min_stock: int = Field(default=5)
    image_path: str | None = Field(default=None, max_length=255)
    active: bool = Field(default=True)

    category: Mapped[Optional["Category"]] = Relationship(back_populates="products")
    sale_details: Mapped[list["SaleDetail"]] = Relationship(back_populates="product")
    inventory_logs: Mapped[list["InventoryLog"]] = Relationship(
        back_populates="product"
    )


from .category import Category  # noqa: E402
from .inventory_log import InventoryLog  # noqa: E402
from .sale_detail import SaleDetail  # noqa: E402
