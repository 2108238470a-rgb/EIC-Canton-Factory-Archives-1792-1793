"""Complete alias, role and historical event evidence projections idempotently."""

from alembic import op
from sqlalchemy.orm import Session
import sqlalchemy as sa

revision = "006_legacy_projections"
down_revision = "005_evidence_images"
branch_labels = None
depends_on = None


def upgrade():
    if "entity_links" not in {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("annotations")
    }:
        op.add_column(
            "annotations",
            sa.Column("entity_links", sa.JSON(), nullable=False, server_default="{}"),
        )
    from app.workbench.legacy import migrate_legacy

    with Session(bind=op.get_bind()) as db:
        migrate_legacy(db)
        db.flush()


def downgrade():
    raise RuntimeError("Restore a verified backup to preserve historical mappings.")
