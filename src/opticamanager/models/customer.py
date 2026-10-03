from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .prescription import Prescription
    from .sale import Sale


class Customer(AuditBase, table=True):
    __tablename__ = "customers"

    id: int | None = Field(default=None, primary_key=True)
    id_document: str = Field(unique=True, max_length=20)
    name: str = Field(max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    address: str | None = None

    prescriptions: Mapped[list["Prescription"]] = Relationship(
        back_populates="customer"
    )
    sales: Mapped[list["Sale"]] = Relationship(back_populates="customer")
