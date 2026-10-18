"""Explicitly reviewed organization and place links on research annotations."""

from alembic import op
import sqlalchemy as sa

revision = "007_annotation_entities"
down_revision = "006_legacy_projections"
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


def downgrade():
    raise RuntimeError("Restore a verified backup to preserve reviewed identity links.")
