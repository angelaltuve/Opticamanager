from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .product import Product


class Category(AuditBase, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=100)
    description: str | None = None

    products: Mapped[list["Product"]] = Relationship(back_populates="category")
