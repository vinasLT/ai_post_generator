from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ad03b432ff70"
down_revision: Union[str, Sequence[str], None] = "5a6fa3941189"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("request_filters") as b:
            b.add_column(sa.Column("auction_date_from", sa.DateTime(timezone=True), nullable=True))
            b.add_column(sa.Column("auction_date_to", sa.DateTime(timezone=True), nullable=True))
            b.alter_column("model", existing_type=sa.VARCHAR(), nullable=True)
    else:
        op.add_column("request_filters", sa.Column("auction_date_from", sa.DateTime(timezone=True), nullable=True))
        op.add_column("request_filters", sa.Column("auction_date_to", sa.DateTime(timezone=True), nullable=True))
        op.alter_column("request_filters", "model", existing_type=sa.VARCHAR(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("request_filters") as b:
            b.alter_column("model", existing_type=sa.VARCHAR(), nullable=False)
            b.drop_column("auction_date_to")
            b.drop_column("auction_date_from")
    else:
        op.alter_column("request_filters", "model", existing_type=sa.VARCHAR(), nullable=False)
        op.drop_column("request_filters", "auction_date_to")
        op.drop_column("request_filters", "auction_date_from")
