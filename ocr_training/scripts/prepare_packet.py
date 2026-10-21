#!/usr/bin/env python3
"""Create a local, blind transcription packet from pilot.json (no DB/API writes)."""
import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path
from PIL import Image

COLUMNS = [
    "sample_id",
    "split_group",
    "volume_id",
    "writer_group",
    "pdf_page",
    "original_page_label",
    "region_id",
    "image_path",
    "page_image_path",
    "reference",
    "annotator",
    "reviewer",
    "status",
    "uncertainty",
    "notes",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(pilots, output):
    if output.exists():
        raise ValueError("输出目录已存在；请使用新目录，避免覆盖人工标注")
    # Validate every source before creating an output packet.
    sources = []
    ids = set()
    for pilot in pilots:
        data = json.loads(pilot.read_text(encoding="utf-8"))
        for page in data["pages"]:
            path = Path(page["image_path"])
            if not path.is_absolute():
                path = pilot.parent / path
            with Image.open(path) as im:
                width, height = im.size
            for block in page["blocks"]:
                sid = (
                    f"doc{data['document_id']}-p{page['pdf_page']}-b{block['block_id']}"
                )
                if sid in ids:
                    raise ValueError(f"重复样本 {sid}")
                ids.add(sid)
                box = block["bbox"]
                if len(box) != 4 or not all(
                    isinstance(v, (int, float)) and math.isfinite(v) for v in box
                ):
                    raise ValueError(f"{sid}: bbox 必须是有限像素坐标 [x1,y1,x2,y2]")
                x1, y1, x2, y2 = box
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                    raise ValueError(
                        f"{sid}: bbox 超出页图；先核对坐标比例，禁止静默缩放"
                    )
                sources.append(
                    (
                        data,
                        page,
                        block,
                        path,
                        sid,
                        (math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2)),
                    )
                )
    if not sources:
        raise ValueError("没有可标注区域")
    output.mkdir(parents=True)
    (output / "images").mkdir()
    (output / "pages").mkdir()
    rows, manifest, hints = [], [], []
    for data, page, block, path, sid, box in sources:
        page_name = f"doc{data['document_id']}-p{page['pdf_page']:04d}.png"
        page_dest = output / "pages" / page_name
        if not page_dest.exists():
            with Image.open(path) as im:
                im.save(page_dest)
        crop_path = output / "images" / f"{sid}.png"
        with Image.open(path) as im:
            im.crop(box).save(crop_path)
        rows.append(
            dict(
                zip(
                    COLUMNS,
                    [
                        sid,
                        f"volume-{data['document_id']}",
                        str(data["document_id"]),
                        "",
                        page["pdf_page"],
                        page.get("original_page_label") or "",
                        block["block_id"],
                        f"images/{sid}.png",
                        f"pages/{page_name}",
                        "",
                        "",
                        "",
                        "draft",
                        "",
                        "",
                    ],
                )
            )
        )
        manifest.append(
            {
                "sample_id": sid,
                "crop_sha256": sha(crop_path),
                "page_sha256": sha(page_dest),
                "bbox_pixels": list(box),
                "source_filename": data["filename"],
                "pdf_page": page["pdf_page"],
                "block_id": block["block_id"],
            }
        )
        hints.append({"sample_id": sid, "raw": block.get("raw") or ""})
    with (output / "annotations.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (output / "manifest.json").write_text(
        json.dumps(
            {"version": 1, "gold_status": "not_labeled", "samples": manifest},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "ocr_hints_do_not_use_as_gold.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in hints),
        encoding="utf-8",
    )
    (output / "开始标注.txt").write_text(
        "先独立看 images/ 区域图，必要时对照 pages/ 全页。annotations.csv 的 reference 留空，等待人工转录。\n不要把 OCR 提示当真值。批准前由另一位人员复核；不清楚的标为 uncertain。\nsplit_group 默认按档案 ID 分组；同一实体卷册重复上传或同一书写者的相关材料必须合并分组。\n坐标来自旧 OCR，可能漏行或裁切不全：请对照整页，存在问题标为 excluded 并说明，重新裁图后再加入。\n",
        encoding="utf-8",
    )
    return len(rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        print(
            f"Prepared {prepare(args.pilot,args.output)} unlabeled samples in {args.output}"
        )
    except (ValueError, KeyError, OSError) as e:
        p.exit(1, f"{e}\n")
