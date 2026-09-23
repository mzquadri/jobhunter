"""Persist conditional source state and independently observed field relevance."""
import sqlalchemy as sa

from alembic import op

revision = "careeros_v3_state"
down_revision = "5b46bd42c71c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_health", sa.Column("fetch_state", sa.JSON(),
                                             nullable=False, server_default="{}"))
    op.add_column("jobs", sa.Column("field_relevance", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("field_evidence", sa.Text(),
                                  nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("requirements", sa.JSON(),
                                  nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for name in ("reviewed_at", "requirements", "field_evidence", "field_relevance"):
        op.drop_column("jobs", name)
    op.drop_column("provider_health", "fetch_state")
