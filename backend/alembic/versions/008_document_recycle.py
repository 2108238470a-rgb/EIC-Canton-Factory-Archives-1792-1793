"""Reversible document removal without breaking historical references."""

from alembic import op
import sqlalchemy as sa

revision = "008_document_recycle"
down_revision = "007_annotation_entities"
branch_labels = None
depends_on = None


def upgrade():
    if "archived_at" not in {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("documents")
    }:
        op.add_column(
            "documents", sa.Column("archived_at", sa.DateTime(), nullable=True)
        )
        op.create_index("ix_documents_archived_at", "documents", ["archived_at"])


def downgrade():
    raise RuntimeError("Restore a verified backup to preserve recycled documents.")
