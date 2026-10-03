from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .customer import Customer
    from .prescription import Prescription
    from .sale_detail import SaleDetail
    from .sale_payment import SalePayment
    from .sale_status import SaleStatus
    from .user import User


class Sale(AuditBase, table=True):
    __tablename__ = "sales"

    id: int | None = Field(default=None, primary_key=True)
    invoice_number: str = Field(unique=True, max_length=50)
    customer_id: int = Field(foreign_key="customers.id")
    user_id: int = Field(foreign_key="users.id")
    status_id: int = Field(foreign_key="sale_statuses.id")
    prescription_id: int | None = Field(default=None, foreign_key="prescriptions.id")

    payment_method: str = Field(
        max_length=30
    )  # Efectivo, Transferencia, Débito, Crédito, Mixto
    amount_received: Decimal | None = Field(default=None, sa_type=Numeric(10, 2))
    change_amount: Decimal | None = Field(default=None, sa_type=Numeric(10, 2))

    subtotal: Decimal = Field(sa_type=Numeric(10, 2))
    taxes: Decimal = Field(sa_type=Numeric(10, 2))
    discount: Decimal = Field(default=0, sa_type=Numeric(10, 2))
    total: Decimal = Field(sa_type=Numeric(10, 2))

    customer: Mapped[Optional["Customer"]] = Relationship(back_populates="sales")
    user: Mapped[Optional["User"]] = Relationship(back_populates="sales")
    status: Mapped[Optional["SaleStatus"]] = Relationship(back_populates="sales")
    prescription: Mapped[Optional["Prescription"]] = Relationship(
        back_populates="sales"
    )
    details: Mapped[list["SaleDetail"]] = Relationship(back_populates="sale")
    payments: Mapped[list["SalePayment"]] = Relationship(back_populates="sale")


from .customer import Customer  # noqa: E402
from .prescription import Prescription  # noqa: E402
from .sale_detail import SaleDetail  # noqa: E402
from .sale_payment import SalePayment  # noqa: E402
from .sale_status import SaleStatus  # noqa: E402
from .user import User  # noqa: E402
