"""Bootstrap original OCR tables; adopt existing installations without deleting data."""

from alembic import op
from app.database import Base
import app.models

revision = "000_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for name in ("documents", "pages", "blocks", "tasks", "exports"):
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError(
        "Baseline rollback is intentionally non-destructive; restore a verified backup."
    )
