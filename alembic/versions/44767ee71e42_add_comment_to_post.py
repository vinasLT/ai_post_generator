from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision = '44767ee71e42'
down_revision = 'b2c7d703a715'
branch_labels = None
depends_on = None

def _has_column(bind, table, column):
    insp = reflection.Inspector.from_engine(bind)
    return any(c["name"] == column for c in insp.get_columns(table))

def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "post", "comment"):
        op.add_column("post", sa.Column("comment", sa.Text(), nullable=True))
    if not _has_column(bind, "post", "year"):
        op.add_column("post", sa.Column("year", sa.Integer(), nullable=True))
        op.execute("update post set year = extract(year from created_at)::int where year is null")
        op.alter_column("post", "year", nullable=False)

def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "post", "comment"):
        op.drop_column("post", "comment")
    if _has_column(bind, "post", "year"):
        op.drop_column("post", "year")
