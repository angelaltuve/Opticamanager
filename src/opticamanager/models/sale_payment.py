from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .sale import Sale


class SalePayment(AuditBase, table=True):
    """Individual payment line of a sale (supports mixed payments).

    Each line records the payment method, the currency it was tendered in
    (``Bs`` or ``USD``), the original amount, and its Bolívar equivalent
    computed at ``rate_used``.
    """

    __tablename__ = "sale_payments"

    id: int | None = Field(default=None, primary_key=True)
    sale_id: int = Field(foreign_key="sales.id")
    method: str = Field(max_length=30)  # Pago Móvil, Zelle, Efectivo Bs, Efectivo USD
    currency: str = Field(max_length=3)  # "Bs" or "USD"
    amount: Decimal = Field(sa_type=Numeric(10, 2))  # amount in `currency`
    amount_bs: Decimal = Field(sa_type=Numeric(10, 2))  # equivalent in Bolívares
    rate_used: Decimal | None = Field(default=None, sa_type=Numeric(10, 2))

    sale: Mapped[Optional["Sale"]] = Relationship(back_populates="payments")


from .sale import Sale  # noqa: E402
