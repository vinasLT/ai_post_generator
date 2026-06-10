"""add broker_fee to post

Revision ID: a1b2c3d4e5f6
Revises: 4b7c08afc72b
Create Date: 2026-06-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '4b7c08afc72b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.add_column(sa.Column('broker_fee', sa.Integer(), nullable=False, server_default='299'))


def downgrade() -> None:
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.drop_column('broker_fee')
