from alembic import op

revision: str = "add_in_progress_to_requeststage"
down_revision = "6c53709783d2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TYPE requeststage ADD VALUE IF NOT EXISTS 'IN_PROGRESS' AFTER 'COMPLETED';")

def downgrade() -> None:
    pass
