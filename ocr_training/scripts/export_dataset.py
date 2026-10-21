#!/usr/bin/env python3
"""Validate independently reviewed crops; export ERNIEKit data with group isolation."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from PIL import Image


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def safe_file(root, relative):
    if not relative or Path(relative).is_absolute():
        raise ValueError("图像必须使用标注包内相对路径")
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError(f"图像不存在或越出标注包: {relative}")
    return p


def validate(packet):
    rows = read_csv(packet / "annotations.csv")
    source = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    entries = source["samples"]
    manifest = {x["sample_id"]: x for x in entries}
    if len(manifest) != len(entries):
        raise ValueError("manifest 存在重复 ID")
    ids = set()
    ready = []
    counts = {}
    for row in rows:
        sid = row.get("sample_id", "")
        if not sid or sid in ids or sid not in manifest:
            raise ValueError(f"无效或重复样本 ID: {sid}")
        ids.add(sid)
        status = row.get("status", "")
        if status not in ["draft", "transcribed", "uncertain", "excluded", "approved"]:
            raise ValueError(f"{sid}: 无效 status")
        counts[status] = counts.get(status, 0) + 1
        image = safe_file(packet, row.get("image_path", ""))
        if (
            hashlib.sha256(image.read_bytes()).hexdigest()
            != manifest[sid]["crop_sha256"]
        ):
            raise ValueError(f"{sid}: 图像已改变，请重新建包并复核")
        with Image.open(image) as im:
            im.verify()
        page = safe_file(packet, row.get("page_image_path", ""))
        if (
            hashlib.sha256(page.read_bytes()).hexdigest()
            != manifest[sid]["page_sha256"]
        ):
            raise ValueError(f"{sid}: 全页图像已改变")
        if status != "approved":
            continue
        text = row.get("reference", "")
        if not text.strip() or row.get("uncertainty", "").strip() or "⟦不清⟧" in text:
            raise ValueError(f"{sid}: 待核验或空转录不得批准")
        if (
            not row.get("annotator", "").strip()
            or not row.get("reviewer", "").strip()
            or row["annotator"].strip() == row["reviewer"].strip()
        ):
            raise ValueError(f"{sid}: 需要不同的标注者和复核者")
        if not row.get("split_group", "").strip():
            raise ValueError(f"{sid}: 缺少 split_group")
        if len(text) > 20000:
            raise ValueError(f"{sid}: 区域过长，请拆分后重新标注")
        ready.append((row, image))
    if ids != set(manifest):
        raise ValueError(
            "annotations.csv 遗失了 manifest 中的样本；请保留行并用 excluded 排除"
        )
    return ready, counts


def export(packet, splits_file, output):
    ready, counts = validate(packet)
    if not ready:
        raise ValueError("没有可导出的 approved 样本")
    rows = read_csv(splits_file)
    splits = {}
    for row in rows:
        group = row.get("split_group", "").strip()
        split = row.get("split", "").strip()
        if not group or group in splits or split not in ["train", "validation", "test"]:
            raise ValueError("分组表需要唯一 split_group 和 train/validation/test")
        splits[group] = split
    seen = {}
    group_checks = {}
    manifest = {
        r["sample_id"]: r
        for r in json.loads((packet / "manifest.json").read_text(encoding="utf-8"))[
            "samples"
        ]
    }
    partition = {k: [] for k in ["train", "validation", "test"]}
    for row, path in ready:
        group = row["split_group"].strip()
        if group not in splits:
            raise ValueError(f"缺少分组映射 {group}")
        split = splits[group]
        for kind, value in [
            ("volume", row.get("volume_id", "")),
            ("writer", row.get("writer_group", "")),
            ("page", manifest[row["sample_id"]]["page_sha256"]),
        ]:
            if not value:
                continue
            key = (kind, value)
            if key in group_checks and group_checks[key] != split:
                raise ValueError(f"同一{kind}跨分组，存在泄漏: {value}")
            group_checks[key] = split
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen and seen[digest] != split:
            raise ValueError("完全相同的图像跨训练/验证/测试集，存在泄漏")
        seen[digest] = split
        partition[split].append((row, path))
    if any(not items for items in partition.values()):
        raise ValueError(
            "训练/验证/测试集都需有独立分组且有 approved 样本；单卷包不能作为跨卷验收"
        )
    if output.exists():
        raise ValueError("输出目录已存在，禁止覆盖")
    output.mkdir(parents=True)
    (output / "images").mkdir()
    hints = {}
    hint_file = packet / "ocr_hints_do_not_use_as_gold.jsonl"
    if hint_file.exists():
        hints = {
            x["sample_id"]: x["raw"]
            for x in map(json.loads, hint_file.read_text(encoding="utf-8").splitlines())
        }
    audit = []
    for split, items in partition.items():
        records = []
        pairs = []
        for row, path in items:
            # Never interpolate editable sample IDs into output paths.
            name = hashlib.sha256(row["sample_id"].encode()).hexdigest() + ".png"
            shutil.copyfile(path, output / "images" / name)
            records.append(
                {
                    "image_info": [
                        {"matched_text_index": 0, "image_url": "images/" + name}
                    ],
                    "text_info": [
                        {"text": "OCR:", "tag": "mask"},
                        {"text": row["reference"], "tag": "no_mask"},
                    ],
                }
            )
            audit.append(
                {
                    "sample_id": row["sample_id"],
                    "split_group": row["split_group"],
                    "split": split,
                    "image_url": "images/" + name,
                    "annotator": row["annotator"],
                    "reviewer": row["reviewer"],
                }
            )
            if row["sample_id"] in hints:
                pairs.append(
                    {
                        "id": row["sample_id"],
                        "raw": hints[row["sample_id"]],
                        "reference": row["reference"],
                    }
                )
        (output / f"{split}.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records),
            encoding="utf-8",
        )
        (output / f"{split}-correction-pairs.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in pairs),
            encoding="utf-8",
        )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "format": "ERNIEKit image-text SFT",
                "cwd_required": "Run dataset loading from this export directory; images use relative paths",
                "model_compatibility": "PaddleOCR-VL-1.6 training/loading not smoke-tested",
                "counts": {k: len(v) for k, v in partition.items()},
                "samples": audit,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {k: len(v) for k, v in partition.items()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--packet", type=Path, required=True)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--splits", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    try:
        if a.check_only:
            ready, counts = validate(a.packet)
            print(
                json.dumps(
                    {"statuses": counts, "export_eligible": len(ready)},
                    ensure_ascii=False,
                )
            )
        else:
            if not a.splits or not a.output:
                p.error("export requires --splits and --output")
            print(export(a.packet, a.splits, a.output))
    except (ValueError, KeyError, OSError) as e:
        p.exit(1, f"{e}\n")
