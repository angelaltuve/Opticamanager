from decimal import Decimal

from sqlalchemy import Numeric
from sqlmodel import Field

from .base import AuditBase


class Supplier(AuditBase, table=True):
    __tablename__ = "suppliers"

    id: int | None = Field(default=None, primary_key=True)
    company_name: str = Field(max_length=150)
    contact_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    address: str | None = None
    current_debt: Decimal = Field(default=0, sa_type=Numeric(10, 2))
    active: bool = Field(default=True)
