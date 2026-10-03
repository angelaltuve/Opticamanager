"""rename cost_price/sale_price to _usd + create app_settings

Revision ID: 23e4b9af3918
Revises: acb589ec2e7e
Create Date: 2026-07-22 16:36:28.695534

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "23e4b9af3918"
down_revision: Union[str, Sequence[str], None] = "acb589ec2e7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename columns in products table (batch mode for SQLite)
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column("cost_price", new_column_name="cost_price_usd")
        batch_op.alter_column("sale_price", new_column_name="sale_price_usd")

    # Create app_settings table
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "value", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False
        ),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("app_settings")
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column("cost_price_usd", new_column_name="cost_price")
        batch_op.alter_column("sale_price_usd", new_column_name="sale_price")
