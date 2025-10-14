"""merge heads

Revision ID: b2c7d703a715
Revises: 6a7f3316ec47, 856e70ca9a07
Create Date: 2025-10-14 16:36:10.091759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c7d703a715'
down_revision: Union[str, Sequence[str], None] = ('6a7f3316ec47', '856e70ca9a07')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
