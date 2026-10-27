"""Canonical research workflow, versioning, preserved legacy migration."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from app.database import Base
import app.models

revision = "003_evidence_workbench"
down_revision = "002_search_chunks_blocks"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    additions = {
        "pages": [
            sa.Column("original_page_label", sa.String(100)),
            sa.Column("folio_side", sa.String(16)),
        ],
        "blocks": [
            sa.Column(
                "retired", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        ],
        "text_revisions": [
            sa.Column(
                "review_state", sa.String(32), nullable=False, server_default="pending"
            )
        ],
        "evidence_spans": [
            sa.Column(
                "validity", sa.String(32), nullable=False, server_default="current"
            ),
            sa.Column("public_id", sa.String(64), unique=True),
            sa.Column("image_snapshot_path", sa.String(512)),
        ],
        "search_chunks": [
            sa.Column("segments", sa.JSON()),
            sa.Column("search_text", sa.Text()),
            sa.Column(
                "review_state", sa.String(32), nullable=False, server_default="pending"
            ),
        ],
    }
    # Reconcile original text fields previously added at application startup.
    additions["source_unit_spans"] = [
        sa.Column("revision_id", sa.Integer(), sa.ForeignKey("text_revisions.id"))
    ]
    additions["documents"] = [sa.Column("full_markdown", sa.Text())]
    additions["blocks"].append(sa.Column("ocr_correction_source_text", sa.Text()))
    for table, columns in additions.items():
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    op.execute(
        "ALTER TABLE entities ALTER COLUMN entity_type TYPE VARCHAR(32) USING entity_type::text"
    )
    # Preserve old vectors separately when dimensions differ. No content is deleted.
    dims = bind.execute(
        sa.text(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid='search_chunks'::regclass AND attname='embedding'"
        )
    ).scalar()
    if dims != 1024:
        op.execute("DROP INDEX IF EXISTS ix_search_chunks_embedding_hnsw")
        op.alter_column(
            "search_chunks", "embedding", new_column_name="legacy_embedding"
        )
        op.add_column("search_chunks", sa.Column("embedding", Vector(1024)))
    # Old block-only unique index prevents paragraph chunks; a unique slot is
    # enforced by indexer row locks instead. Existing rows remain recoverable.
    op.execute("DROP INDEX IF EXISTS ix_search_chunks_block_id")
    for constraint in sa.inspect(bind).get_unique_constraints("search_chunks"):
        if constraint["column_names"] == ["block_id"]:
            op.drop_constraint(constraint["name"], "search_chunks", type_="unique")
    for name in (
        "annotations",
        "annotation_reviews",
        "legacy_knowledge_map",
        "research_corpora",
        "corpus_memberships",
        "extraction_leases",
    ):
        Base.metadata.tables[name].create(bind, checkfirst=True)
    op.execute("UPDATE search_chunks SET status='INVALIDATED'")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_chunks_embedding_hnsw ON search_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_chunks_search_text_fts ON search_chunks USING gin (to_tsvector('simple', coalesce(search_text, '')))"
    )
    from app.workbench.legacy import migrate_legacy
    from sqlalchemy.orm import Session

    with Session(bind=bind) as db:
        migrate_legacy(db)
        db.flush()


def downgrade():
    raise RuntimeError(
        "This migration preserves historical records. Restore a verified backup for rollback."
    )
