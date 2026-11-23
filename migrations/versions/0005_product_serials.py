"""Serial records for product domains, editable with preserved history."""
from alembic import op
import sqlalchemy as sa

revision = "0005_serials"
down_revision = "0004_library"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("domain_serial_policies", sa.Column("tt", sa.String(2), primary_key=True),
                    sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("serial_prefix", sa.String(80), nullable=False))
    op.execute("INSERT INTO domain_serial_policies VALUES ('19',1,''),('20',1,''),('29',1,'')")
    op.execute("DROP TRIGGER unit_identity_frozen")
    op.add_column("physical_units", sa.Column("serial_scope", sa.String(50), nullable=True))
    op.add_column("physical_units", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE physical_units SET serial_scope = CASE WHEN part_id IS NOT NULL THEN 'part:' || part_id ELSE 'board:' || board_id END")
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("physical_units", naming_convention=convention) as batch:
        batch.drop_constraint("uq_physical_units_serial_key", type_="unique")
        batch.drop_constraint("ck_unit_release_required", type_="check")
        batch.alter_column("board_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("serial_scope", existing_type=sa.String(50), nullable=False)
        batch.alter_column("archived", existing_type=sa.Boolean(), server_default=None)
        batch.create_unique_constraint("uq_unit_scope_serial", ["serial_scope", "serial_key"])
        batch.create_check_constraint("ck_unit_owner", "board_id IS NOT NULL OR part_id IS NOT NULL")
        batch.create_check_constraint("ck_unit_release_required", "historical OR release_id IS NOT NULL OR board_id IS NULL")
        batch.create_check_constraint("ck_unit_status", "status IN ('active','in-test','faulty','repaired','retired','waste')")
    op.execute("""CREATE TRIGGER unit_identity_frozen BEFORE UPDATE ON physical_units
        WHEN NEW.part_id IS NOT OLD.part_id OR NEW.serial_scope IS NOT OLD.serial_scope OR
        (OLD.board_id IS NOT NULL AND NEW.board_id IS NOT OLD.board_id) OR NEW.historical IS NOT OLD.historical OR
        (OLD.release_id IS NOT NULL AND NEW.release_id IS NOT OLD.release_id)
        BEGIN SELECT RAISE(ABORT, 'Unit ownership and resolved revision are immutable'); END""")
    op.execute("""CREATE TRIGGER unit_serial_audit BEFORE UPDATE ON physical_units
        WHEN (NEW.serial IS NOT OLD.serial OR NEW.serial_key IS NOT OLD.serial_key) AND NOT EXISTS (
        SELECT 1 FROM unit_events WHERE unit_id=OLD.id AND kind='edit'
        AND json_extract(details_json, '$.before.serial')=OLD.serial
        AND json_extract(details_json, '$.after.serial')=NEW.serial
        AND id=(SELECT max(id) FROM unit_events WHERE unit_id=OLD.id))
        BEGIN SELECT RAISE(ABORT, 'Serial corrections require a history event'); END""")


def downgrade():
    raise RuntimeError("Restore a verified backup to downgrade")
