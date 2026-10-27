"""Exercise fresh and legacy PostgreSQL migrations in disposable databases."""

import os
import subprocess
import sys
from pathlib import Path
import uuid
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import Base
from app.models import LegacyMapping, EvidenceSpan
from app.knowledge.models import (
    CanonicalEntity,
    EntityName,
    EvidenceSpan as OldEvidence,
)
from app.knowledge.enums import EntityType


def main():
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    results = []
    for legacy in (False, True):
        name = "ocr_workbench_test_" + uuid.uuid4().hex[:12]
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        url = admin.url.set(database=name)
        env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
        test_engine = None
        try:

            def migrate(target):
                result = subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", target],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)

            migrate("002_search_chunks_blocks" if legacy else "head")
            test_engine = create_engine(url)
            if legacy:
                for table in Base.metadata.sorted_tables:
                    if table.name.startswith("knowledge_"):
                        table.create(test_engine, checkfirst=True)
                with test_engine.begin() as c:
                    c.execute(
                        text(
                            "INSERT INTO documents(id,filename,original_filename,file_path,file_type,file_size,page_count,status) VALUES(1,'legacy.pdf','Legacy archive','/tmp/legacy.pdf','PDF',1,1,'COMPLETED')"
                        )
                    )
                    c.execute(
                        text(
                            "INSERT INTO pages(id,document_id,page_number) VALUES(1,1,1)"
                        )
                    )
                    c.execute(
                        text(
                            "INSERT INTO blocks(id,page_id,block_index,bbox,ocr_text_raw,review_status,retired) VALUES(1,1,0,'[0,0,10,10]','Captain Smith sent a request.','PENDING',false)"
                        )
                    )
                with test_engine.begin() as c:
                    c.execute(
                        text(
                            "INSERT INTO search_chunks(content,content_hash,embedding,embedding_model,status) VALUES('preserved legacy snippet','legacy-hash',CAST(:vector AS vector),'legacy-model','INDEXED')"
                        ),
                        {"vector": "[" + ",".join(["0"] * 1536) + "]"},
                    )
                with Session(test_engine) as db:
                    entity = CanonicalEntity(
                        entity_type=EntityType.PERSON, canonical_name="Smith"
                    )
                    db.add(entity)
                    db.flush()
                    db.add(EntityName(entity_id=entity.id, name="Captain Smith"))
                    db.add(
                        OldEvidence(
                            public_id="legacy-evidence-1",
                            document_id=1,
                            page_id=1,
                            block_id=1,
                            text_version="ocr_raw",
                            char_start=0,
                            char_end=13,
                            excerpt="Captain Smith",
                        )
                    )
                    db.commit()
                migrate("head")
                with Session(test_engine) as db:
                    preserved = db.execute(
                        text(
                            "SELECT content,legacy_embedding IS NOT NULL,embedding IS NULL,status FROM search_chunks WHERE content_hash='legacy-hash'"
                        )
                    ).one()
                    assert tuple(preserved) == (
                        "preserved legacy snippet",
                        True,
                        True,
                        "INVALIDATED",
                    )
                    assert db.query(EvidenceSpan).one().validity == "legacy_unverified"
                    assert (
                        db.query(LegacyMapping)
                        .filter_by(source_table="knowledge_entities")
                        .one()
                        .new_id
                        is not None
                    )
                    assert (
                        db.execute(
                            text("SELECT count(*) FROM knowledge_evidence_spans")
                        ).scalar()
                        == 1
                    )
                    assert (
                        db.execute(text("SELECT count(*) FROM documents")).scalar() == 1
                    )
                    assert (
                        db.execute(
                            text(
                                "SELECT atttypmod FROM pg_attribute WHERE attrelid='search_chunks'::regclass AND attname='embedding'"
                            )
                        ).scalar()
                        == 1024
                    )
            migrate("head")
            if not legacy:
                test_env = {
                    **env,
                    "WORKBENCH_TEST_DATABASE_URL": url.render_as_string(
                        hide_password=False
                    ),
                }
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "tests",
                        "-p",
                        "test_workbench.py",
                        "-q",
                    ],
                    env=test_env,
                    capture_output=True,
                    text=True,
                )
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
                results.append("PostgreSQL workflow tests: PASS")
            assert "revision_id" in {
                c["name"] for c in inspect(test_engine).get_columns("source_unit_spans")
            }
            results.append(("legacy" if legacy else "fresh") + " migration: PASS")
        finally:
            if test_engine:
                test_engine.dispose()
            with admin.connect() as c:
                c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    print("\n".join(results))


if __name__ == "__main__":
    main()
