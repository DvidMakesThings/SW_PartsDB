"""Use the existing hardware DOCUMENT_ID instead of a separately entered code."""
from alembic import op
import sqlalchemy as sa

revision = "0008_document_id"
down_revision = "0007_builds"
branch_labels = None
depends_on = None


def upgrade():
    # Existing project codes, links and serial labels are retained. Their full
    # document IDs cannot be reconstructed without the source board/revision.
    op.add_column("design_projects", sa.Column("document_id", sa.String(100), nullable=True))


def downgrade():
    raise RuntimeError("Restore a verified backup to downgrade")
