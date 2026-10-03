"""add payment method to sales

Revision ID: 99721edb5ec3
Revises: 53180373ae4f
Create Date: 2026-09-17 12:04:26.573227

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "99721edb5ec3"
down_revision: Union[str, Sequence[str], None] = "53180373ae4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("sales", schema=None) as batch_op:
        # Existing rows get a default payment method. The value has to match
        # EFECTIVO_BS in ui/views/pos_view.py so that payment-method groupings
        # stay consistent.
        batch_op.add_column(
            sa.Column(
                "payment_method",
                sqlmodel.sql.sqltypes.AutoString(length=30),
                server_default="Efectivo Bs",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("amount_received", sa.Numeric(10, 2), nullable=True)
        )
        batch_op.add_column(
            sa.Column("change_amount", sa.Numeric(10, 2), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema.

    WARNING: destructive once sales with payments exist. The ``sale_payments``
    rows (migration 53180373ae4f) are left pointing at payment columns that no
    longer exist. Use this only on empty or development databases.
    """
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_column("payment_method")
        batch_op.drop_column("amount_received")
        batch_op.drop_column("change_amount")
