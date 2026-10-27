"""Pin segmented sources to immutable revisions for early 003 installations."""

from alembic import op
import sqlalchemy as sa

revision = "004_source_revision"
down_revision = "003_evidence_workbench"
branch_labels = None
depends_on = None


def upgrade():
    if "revision_id" not in {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("source_unit_spans")
    }:
        op.add_column(
            "source_unit_spans",
            sa.Column("revision_id", sa.Integer(), sa.ForeignKey("text_revisions.id")),
        )


def downgrade():
    raise RuntimeError("Restore a verified backup to preserve provenance.")
