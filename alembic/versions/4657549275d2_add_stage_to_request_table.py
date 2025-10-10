from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4657549275d2"
down_revision = "ad03b432ff70"
branch_labels = None
depends_on = None

def upgrade() -> None:
    requeststage = postgresql.ENUM(
        "STARTING",
        "FILTERING_BY_TEXT",
        "GENERATION_IMAGES_DESCRIPTION",
        "FILTERING_WITH_IMAGES_DESCRIPTION",
        "COMPLETED",
        name="requeststage",
    )
    bind = op.get_bind()
    requeststage.create(bind, checkfirst=True)
    op.add_column("request_filters", sa.Column("stage", requeststage, nullable=True))

def downgrade() -> None:
    op.drop_column("request_filters", "stage")
    bind = op.get_bind()
    requeststage = postgresql.ENUM(name="requeststage")
    requeststage.drop(bind, checkfirst=True)
