"""create sale_payments

Revision ID: 53180373ae4f
Revises: 23e4b9af3918
Create Date: 2026-09-02 09:49:53.310486

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "53180373ae4f"
down_revision: Union[str, Sequence[str], None] = "23e4b9af3918"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sale_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column(
            "method", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False
        ),
        sa.Column(
            "currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_bs", sa.Numeric(10, 2), nullable=False),
        sa.Column("rate_used", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("sale_payments")
