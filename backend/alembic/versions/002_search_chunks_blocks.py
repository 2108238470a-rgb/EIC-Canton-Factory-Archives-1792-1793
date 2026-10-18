"""Add OCR linkage without deleting stored snippets or changing existing vectors."""

from alembic import op
import sqlalchemy as sa

revision = "002_search_chunks_blocks"
down_revision = "001_knowledge_workbench"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("search_chunks")}
    for name, target in [
        ("document_id", "documents"),
        ("page_id", "pages"),
        ("block_id", "blocks"),
    ]:
        if name not in columns:
            op.add_column("search_chunks", sa.Column(name, sa.Integer(), nullable=True))
            op.create_foreign_key(
                "fk_search_chunks_" + name,
                "search_chunks",
                target,
                [name],
                ["id"],
                ondelete="CASCADE",
            )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_chunks_content_fts ON search_chunks USING gin (to_tsvector('simple', content))"
    )


def downgrade():
    raise RuntimeError(
        "Restore a verified backup to downgrade without losing provenance."
    )
