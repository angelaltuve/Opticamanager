from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship

from .base import AuditBase

if TYPE_CHECKING:
    from .customer import Customer
    from .sale import Sale


class Prescription(AuditBase, table=True):
    __tablename__ = "prescriptions"

    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customers.id")

    od_sphere: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))
    od_cylinder: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))
    od_axis: int | None = Field(default=None)
    od_addition: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))

    os_sphere: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))
    os_cylinder: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))
    os_axis: int | None = Field(default=None)
    os_addition: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))

    pupillary_distance: Decimal | None = Field(default=None, sa_type=Numeric(4, 2))
    issued_date: date = Field()
    notes: str | None = None

    customer: Mapped[Optional["Customer"]] = Relationship(
        back_populates="prescriptions"
    )
    sales: Mapped[list["Sale"]] = Relationship(back_populates="prescription")


from .customer import Customer  # noqa: E402
