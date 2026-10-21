"""Document workspace APIs. No model call happens on a read request."""

import copy
import json
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import ExtractionRun, ExtractionStatus
from app.insights.service import (
    SCHEMA,
    document,
    snapshot,
    request_analysis,
    get_run,
    payload,
)

router = APIRouter(prefix="/insights", tags=["document-insights"])


class AnalysisRequest(BaseModel):
    mode: Literal["directory", "ai"] = "directory"
    force: bool = False


class TocEdit(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    expected_revision: int = Field(ge=1)


def dispatch(db, run):
    from app.tasks.insight_tasks import analyze_document

    try:
        analyze_document.delay(run.id)
    except Exception:
        run.status = ExtractionStatus.FAILED
        run.error_message = "任务队列不可用，请恢复 Celery/Redis 后重试"
        db.commit()


@router.get("/documents/{doc_id}")
def workspace(doc_id: int, db: Session = Depends(get_db)):
    doc = document(db, doc_id)
    sources = snapshot(db, doc_id)
    runs = (
        db.query(ExtractionRun)
        .filter_by(document_id=doc_id, schema_version=SCHEMA)
        .order_by(ExtractionRun.id.desc())
        .limit(30)
        .all()
    )
    result = {
        "document_id": doc_id,
        "title": doc.original_filename,
        "page_count": doc.page_count,
        "text_pages": len({s["page_number"] for s in sources}),
        "text_blocks": len(sources),
        "runs": [
            {
                "id": r.id,
                "status": r.status.value,
                "mode": (r.parameters or {}).get("mode"),
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ],
        "latest": payload(db, runs[0]) if runs else None,
    }
    db.commit()  # persist immutable snapshots for legacy blocks when needed
    return result


@router.post("/documents/{doc_id}")
def create(doc_id: int, data: AnalysisRequest, db: Session = Depends(get_db)):
    run, created = request_analysis(db, doc_id, data.mode, data.force)
    db.commit()
    if created and data.mode == "ai":
        dispatch(db, run)
    return payload(db, run)


@router.get("/runs/{run_id}")
def read(run_id: int, db: Session = Depends(get_db)):
    result = payload(db, get_run(db, run_id))
    db.commit()
    return result


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: int, db: Session = Depends(get_db)):
    run = get_run(db, run_id)
    db.query(ExtractionRun).filter(
        ExtractionRun.id == run.id,
        ExtractionRun.status.in_([ExtractionStatus.PENDING, ExtractionStatus.RUNNING]),
    ).update(
        {"status": ExtractionStatus.CANCELLED, "completed_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(run)
    return payload(db, run)


@router.post("/runs/{run_id}/retry")
def retry(run_id: int, db: Session = Depends(get_db)):
    run = get_run(db, run_id)
    if payload(db, run)["stale"]:
        raise HTTPException(409, "原文已更新，请新建分析版本")
    if (run.parameters or {}).get("mode") != "ai":
        raise HTTPException(409, "目录版本不需要重试")
    updated = (
        db.query(ExtractionRun)
        .filter(
            ExtractionRun.id == run.id,
            ExtractionRun.status.in_(
                [ExtractionStatus.FAILED, ExtractionStatus.CANCELLED]
            ),
        )
        .update(
            {
                "status": ExtractionStatus.PENDING,
                "error_message": None,
                "batch_id": str(uuid4()),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    db.refresh(run)
    if updated:
        dispatch(db, run)
    return payload(db, run)


@router.patch("/runs/{run_id}/toc/{entry_id}")
def edit_toc(run_id: int, entry_id: str, data: TocEdit, db: Session = Depends(get_db)):
    run = get_run(db, run_id)
    # The base run is locked while allocating its single successor. Old artifacts stay immutable.
    run = (
        db.query(ExtractionRun)
        .filter_by(id=run.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if run.status != ExtractionStatus.COMPLETED or payload(db, run)["stale"]:
        raise HTTPException(409, "请先完成分析，或基于当前原文生成新版本")
    artifact = copy.deepcopy(run.output_summary)
    if artifact["revision"] != data.expected_revision or (run.parameters or {}).get(
        "successor_id"
    ):
        raise HTTPException(409, "目录已有新版本，请刷新后再编辑")
    entries = artifact["toc"] + [i for i in artifact["items"] if i["kind"] == "topic"]
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        raise HTTPException(404, "目录条目不存在")
    title = data.title.strip()
    if not title:
        raise HTTPException(422, "标题不能为空")
    before = entry["title"]
    entry["title"] = title
    entry["review_status"] = (
        "edited_unverified"  # renaming never approves historical claims
    )
    artifact["revision"] += 1
    child = ExtractionRun(
        document_id=run.document_id,
        schema_version=SCHEMA,
        input_hash=run.input_hash,
        input_version_ids=run.input_version_ids,
        model_name=run.model_name,
        model_version=run.model_version,
        prompt_template=run.prompt_template,
        parameters={
            "mode": (run.parameters or {}).get("mode"),
            "parent_run_id": run.id,
            "edit": {
                "entry_id": entry_id,
                "before": before,
                "after": title,
                "at": datetime.utcnow().isoformat(),
                "author": "local_researcher",
            },
        },
        output_summary=artifact,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime.utcnow(),
    )
    db.add(child)
    db.flush()
    run.parameters = {**(run.parameters or {}), "successor_id": child.id}
    db.commit()
    return payload(db, child)


@router.get("/runs/{run_id}/export")
def export(
    run_id: int,
    format: Literal["json", "markdown"] = Query("json"),
    db: Session = Depends(get_db),
):
    result = payload(db, get_run(db, run_id))
    result["manifest"] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "exported_at": datetime.utcnow().isoformat(),
        "warning": "AI候选解释不等于人工核实事实；引句有效不等于结论已被证明",
    }
    if format == "json":
        content = json.dumps(result, ensure_ascii=False, indent=2)
        media, suffix = "application/json", "json"
    else:
        lines = [
            f"# 文献研究分析 #{result['document_id']}",
            f"版本 {run_id} · 原文状态：{'已过时' if result['stale'] else '当前版本'}",
            result["manifest"]["warning"],
            "",
            "## 目录与研究线索",
        ]
        for paragraph in result["artifact"].get("summary", []):
            lines += ["## 全文概述 · AI候选", paragraph["text"]]
            for source in paragraph["sources"]:
                lines += [
                    f"> {source['quote']}",
                    f"来源：第{source['page_number']}页 / 区块{source['block_id']} / 文本版本{source['revision_id']}",
                ]
        for item in result["artifact"]["toc"] + result["artifact"]["items"]:
            lines += [
                f"### {item['title']}",
                item.get("description", ""),
                f"日期：{item.get('date') or '未确定'}；依据：{item.get('date_basis', 'unknown')}",
            ]
            for s in item["sources"]:
                lines += [
                    f"> {s['quote']}",
                    f"[第{s['page_number']}页 / 区块{s['block_id']} / 版本{s['revision_id']}]"
                    f"(/viewer/{result['document_id']}?page={s['page_number']}&block={s['block_id']})",
                ]
        lines += [
            "",
            "## 覆盖与局限",
            json.dumps(
                {
                    k: v
                    for k, v in result["artifact"].items()
                    if k not in {"toc", "items"}
                },
                ensure_ascii=False,
            ),
        ]
        content, media, suffix = "\n\n".join(lines), "text/markdown", "md"
    db.commit()
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="research-{run_id}.{suffix}"'
        },
    )
