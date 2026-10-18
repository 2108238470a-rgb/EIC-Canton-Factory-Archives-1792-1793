import sys

"""Prepare a reproducible 30–50 page, unlabeled human evaluation packet.

This reads the archive but never changes its metadata, approvals or indexes.
"""

import argparse, csv, hashlib, json
from datetime import datetime
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Document, Page, Block
from app.workbench.api import EXPORT_COLUMNS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", type=int, required=True)
    parser.add_argument("--pages", type=int, default=40)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 30 <= args.pages <= 50:
        parser.error("--pages must be between 30 and 50")
    args.output.mkdir(parents=True, exist_ok=False)
    with SessionLocal() as db:
        doc = db.get(Document, args.document)
        if not doc:
            parser.error("document not found")
        records = []
        for page in (
            db.query(Page).filter_by(document_id=doc.id).order_by(Page.page_number)
        ):
            blocks = (
                db.query(Block)
                .filter_by(page_id=page.id, retired=False)
                .order_by(Block.block_index)
                .all()
            )
            prose = [
                b
                for b in blocks
                if (b.ocr_text_corrected or b.ocr_text_raw or "").strip()
            ]
            if not prose:
                continue
            records.append(
                {
                    "page_id": page.id,
                    "pdf_page": page.page_number,
                    "original_page_label": page.original_page_label,
                    "image_path": page.image_path,
                    "reviewer_tags": [],
                    "blocks": [
                        {
                            "block_id": b.id,
                            "bbox": b.bbox,
                            "raw": b.ocr_text_raw,
                            "corrected": b.ocr_text_corrected,
                            "review_status": b.review_status.value,
                            "confidence": b.confidence,
                            "text_sha256": hashlib.sha256(
                                (b.ocr_text_corrected or b.ocr_text_raw or "").encode()
                            ).hexdigest(),
                        }
                        for b in prose
                    ],
                }
            )
        selected = []

        def add(record):
            if len(selected) < args.pages and record["page_id"] not in {
                p["page_id"] for p in selected
            }:
                selected.append(record)

        # Keep a contiguous passage for cross-page review, then spread across the
        # volume and include difficult pages. These are candidate strata, not labels.
        for r in records[:5]:
            add(r)
        if records:
            for i in range(min(len(records), args.pages - 10)):
                add(records[round(i * (len(records) - 1) / max(1, args.pages - 11))])
        for r in sorted(
            records,
            key=lambda r: min(
                (
                    b["confidence"] if b["confidence"] is not None else 1
                    for b in r["blocks"]
                ),
                default=1,
            ),
        )[:5]:
            add(r)
        for r in sorted(
            records,
            key=lambda r: sum(
                len(b["corrected"] or b["raw"] or "") for b in r["blocks"]
            ),
            reverse=True,
        ):
            add(r)
        selected.sort(key=lambda r: r["pdf_page"])
        packet = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "document_id": doc.id,
            "filename": doc.original_filename,
            "date_coverage_verified": False,
            "eligible_pages": len(records),
            "selected_pages": len(selected),
            "selection": "contiguous + volume spread + low OCR confidence + dense pages",
            "human_gold_status": "not_labeled",
            "pages": selected,
            "queries": [],
        }
        (args.output / "pilot.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2)
        )
        with (args.output / "annotation_template.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as output:
            csv.writer(output).writerow(EXPORT_COLUMNS)
        summary = {
            "selected_pages": len(selected),
            "blocks": sum(len(p["blocks"]) for p in selected),
            "reviewed_blocks": sum(
                b["review_status"] == "approved" for p in selected for b in p["blocks"]
            ),
            "gold_queries": 0,
            "entity_f1": None,
            "recall_at_k": None,
            "citation_support_rate": None,
            "reason": "Independent historical annotations and adjudication are required before quality metrics can be reported.",
        }
        (args.output / "baseline.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )
        (args.output / "README.md").write_text(
            """# 40 页历史档案试点材料

文件名只用于选择候选卷册，不代表已核实日期覆盖范围。分层选页是候选，尚未由研究者确认清晰度、跨页来函、缩写、同名与身份冲突等类别。

1. 两位研究者独立标注文书边界、人物/事件/角色、身份和原文证据，由第三人裁决分歧。
2. 以文书为单位划分开发/测试集，跨页文书不得拆到两边。消歧另分已见与未见人物。
3. 在 pilot.json 的 queries 增加 question、scope、answerable、gold_block_ids、expected_claims；包含中文问英文、无答案和冲突来源题。
4. 在工作台选定文档/页段抽取，人工复核文本与知识，再重建索引；分别评估关键词、语义和混合检索。
5. 记录实体/事件/角色 P/R/F1、身份链接错误合并率、日期准确率、Recall@k、回答支持率、定位正确率、拒答表现、人工复核时间及 tokens。

baseline.json 中的 null 表示尚未具备独立金标准，不能解释为 0 或通过验收。测试不自动调用付费模型，也不改变工作库审核状态。
"""
        )
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
