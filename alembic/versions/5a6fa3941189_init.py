from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "5a6fa3941189"
down_revision = "856e70ca9a07"
branch_labels = None
depends_on = None

def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in insp.get_table_names()

def upgrade():
    if not _table_exists("request_filters"):
        op.create_table(
            "request_filters",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_uuid", sa.String(), nullable=False),
            sa.Column("site", sa.String(length=6), nullable=False),
            sa.Column("make", sa.String(), nullable=False),
            sa.Column("model", sa.String(), nullable=False),
            sa.Column("year_from", sa.Integer(), nullable=True),
            sa.Column("year_to", sa.Integer(), nullable=True),
            sa.Column("odo_from", sa.Integer(), nullable=True),
            sa.Column("odo_to", sa.Integer(), nullable=True),
            sa.Column("document", sa.String(), nullable=True),
            sa.Column("transmission", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

def downgrade():
    if _table_exists("request_filters"):
        op.drop_table("request_filters")
