"""vendedor permissions: pos only

Revision ID: b7c1d4e9f210
Revises: 99721edb5ec3
Create Date: 2026-09-29

The Vendedor role is now limited to the POS section in
``_ROLE_VISIBLE_SECTIONS`` (``ui/main_window.py``). The ``permissions`` column
is descriptive rather than enforced, but leaving "sales,products,reports" in
existing databases would misreport what the role can do. The seeds and
``register_admin`` only create a role when it is missing, so they never reach
rows that already exist.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c1d4e9f210"
down_revision: Union[str, Sequence[str], None] = "99721edb5ec3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_PERMISSIONS = "sales,products,reports"
_NEW_PERMISSIONS = "pos"


def upgrade() -> None:
    """Align the stored permissions with the enforced sidebar access."""
    op.execute(
        sa.text(
            "UPDATE roles SET permissions = :new WHERE name = 'Vendedor'"
        ).bindparams(new=_NEW_PERMISSIONS)
    )


def downgrade() -> None:
    """Restore the previous descriptive permissions string."""
    op.execute(
        sa.text(
            "UPDATE roles SET permissions = :old WHERE name = 'Vendedor'"
        ).bindparams(old=_OLD_PERMISSIONS)
    )
