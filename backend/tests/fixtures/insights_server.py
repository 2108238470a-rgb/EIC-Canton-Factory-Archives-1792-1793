"""Disposable browser acceptance server. No production DB, provider or archive IO."""

import asyncio, json
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.responses import Response
from app.database import Base
from app.api.deps import get_db
from app.models import Document, DocumentType, Page, Block
from app.insights.api import router
from app.insights.service import analyze
import app.insights.api as api
import app.insights.service as service

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Base.metadata.create_all(engine)
Sessions = sessionmaker(bind=engine, autoflush=False)
with Sessions() as db:
    d = Document(
        id=90001,
        filename="e2e.pdf",
        original_filename="隔离测试文献 · 非生产档案",
        file_path="/tmp/e2e.pdf",
        file_type=DocumentType.PDF,
        file_size=100,
        page_count=2,
    )
    db.add(d)
    db.flush()
    for n, text in enumerate(
        [
            "24 September 1792. Henry Browne sent a letter to Canton.",
            "The committee discussed bills of exchange.",
        ],
        1,
    ):
        p = Page(document_id=d.id, page_number=n)
        db.add(p)
        db.flush()
        db.add(
            Block(page_id=p.id, block_index=0, bbox=[0, 0, 100, 100], ocr_text_raw=text)
        )
    db.commit()


async def model(prompt, text, **kwargs):
    entries = json.loads(text)
    if kwargs.get("mode") == "historical_insights_summary":
        value = {
            "sections": [
                {
                    "text": "这份测试文献记录了 Henry Browne 的函件往来，以及委员会对汇票的讨论。以上概述为 AI 候选，需核对引句。",
                    "source_ids": [entries[0]["id"]],
                }
            ]
        }
    else:
        s = entries[0]
        quote = s["text"]
        value = {
            "items": [
                {
                    "kind": kind,
                    "title": title,
                    "description": "依据测试原文记载的商馆函件线索。",
                    "revision_id": s["revision_id"],
                    "quote": quote,
                    "char_start": 0,
                    "date": "1792-09-24",
                    "date_quote": "24 September 1792",
                    "date_basis": "event_explicit",
                    "people": ["Henry Browne"],
                }
                for kind, title in [
                    ("overview", "商馆函件与结算"),
                    ("topic", "函件往来"),
                    ("event", "寄送函件"),
                ]
            ]
        }
    return SimpleNamespace(
        text=json.dumps(value, ensure_ascii=False),
        token_usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


service.gpt_service.complete = model


# The API's normal dispatch boundary is replaced ONLY in this disposable process.
def dispatch(db, run):
    asyncio.run(analyze(db, run.id))
    db.refresh(run)


api.dispatch = dispatch
app = FastAPI()
app.include_router(router, prefix="/api/v2")


def session():
    with Sessions() as db:
        yield db


app.dependency_overrides[get_db] = session


@app.get("/api/pages/{id}/image")
def image(id: int):
    return Response(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="#f5f1e5"/><text x="24" y="70" font-size="22">ISOLATED TEST FIXTURE</text><text x="24" y="120">24 September 1792</text></svg>',
        media_type="image/svg+xml",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8009, log_level="warning")
