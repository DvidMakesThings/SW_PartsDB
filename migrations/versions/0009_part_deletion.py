"""Allow component deletion without an opening stock count blocking it."""
from alembic import op
import sqlalchemy as sa

revision = "0009_part_deletion"
down_revision = "0008_document_id"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stock_holdings") as batch:
        batch.add_column(sa.Column("deleted_dmtuid", sa.String(20), nullable=True))
        batch.alter_column("dmtuid", existing_type=sa.String(20), nullable=True)


def downgrade():
    raise RuntimeError("Restore a verified backup to downgrade")
