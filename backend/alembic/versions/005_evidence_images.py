"""Preserve image versions behind stable evidence links."""

from alembic import op
import sqlalchemy as sa

revision = "005_evidence_images"
down_revision = "004_source_revision"
branch_labels = None
depends_on = None


def upgrade():
    if "image_snapshot_path" not in {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("evidence_spans")
    }:
        op.add_column(
            "evidence_spans", sa.Column("image_snapshot_path", sa.String(512))
        )


def downgrade():
    raise RuntimeError(
        "Restore a verified backup to preserve historical image versions."
    )
