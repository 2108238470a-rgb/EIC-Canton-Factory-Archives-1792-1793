#!/usr/bin/env python3
"""Rescale stored PDF block bboxes from PaddleOCR's canvas to the stored page image.

Dry run by default; pass --apply to write. Pages whose bboxes already exceed the
PaddleOCR canvas are treated as already fixed and skipped, so reruns are safe.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

TOLERANCE = 0.01


def page_scale(pruned_path: Optional[str], width: Optional[int], height: Optional[int]) -> Optional[Tuple[float, float, float, float]]:
    """Return (scale_x, scale_y, src_width, src_height) or None when no rescale is needed.

    Args:
        pruned_path: Path to the page's pruned_result.json.
        width: Stored page image width.
        height: Stored page image height.

    Returns:
        Scale factors and source canvas size, or None.
    """
    if not pruned_path or not width or not height or not Path(pruned_path).exists():
        return None
    data = json.loads(Path(pruned_path).read_text(encoding="utf-8"))
    src_w, src_h = data.get("width"), data.get("height")
    if not isinstance(src_w, (int, float)) or not isinstance(src_h, (int, float)) or src_w <= 0 or src_h <= 0:
        return None
    sx, sy = width / src_w, height / src_h
    if abs(sx - 1) < TOLERANCE and abs(sy - 1) < TOLERANCE:
        return None
    return sx, sy, float(src_w), float(src_h)


def raw_boxes(pruned_path: str) -> List[List[float]]:
    """Collect every 4-number bbox PaddleOCR recorded in pruned_result.json.

    Args:
        pruned_path: Path to the page's pruned_result.json.

    Returns:
        Raw bboxes in PaddleOCR's canvas.
    """
    data = json.loads(Path(pruned_path).read_text(encoding="utf-8"))
    found: List[List[float]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    key in ("block_bbox", "coordinate", "bbox")
                    and isinstance(value, list)
                    and len(value) == 4
                    and all(isinstance(v, (int, float)) for v in value)
                ):
                    found.append([float(v) for v in value])
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found


def _matches(bbox: list, raw: List[List[float]], sx: float, sy: float) -> bool:
    return any(
        abs(bbox[0] - r[0] * sx) < 0.5
        and abs(bbox[1] - r[1] * sy) < 0.5
        and abs(bbox[2] - r[2] * sx) < 0.5
        and abs(bbox[3] - r[3] * sy) < 0.5
        for r in raw
    )


def page_state(pruned_path: str, blocks: List[Tuple[int, list]], sx: float, sy: float) -> str:
    """Classify a page as 'raw' (needs fixing), 'fixed', or 'unknown'.

    Compares stored bboxes against PaddleOCR's original bboxes, unscaled and scaled.
    """
    raw = raw_boxes(pruned_path)
    valid = [bbox for _, bbox in blocks if bbox and len(bbox) >= 4]
    if not raw or not valid:
        return "unknown"
    if all(_matches(bbox, raw, 1.0, 1.0) for bbox in valid):
        return "raw"
    if all(_matches(bbox, raw, sx, sy) for bbox in valid):
        return "fixed"
    return "unknown"


def main() -> None:
    """Scan PDF pages and rescale misaligned bboxes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes to the database")
    args = parser.parse_args()

    stats = {"pages_fixed": 0, "blocks_fixed": 0, "pages_skipped_done": 0, "pages_unknown": 0, "pages_ok": 0}
    with engine.begin() as conn:
        pages = conn.execute(text(
            "SELECT p.id, p.width, p.height, p.pruned_result_path FROM pages p "
            "JOIN documents d ON d.id = p.document_id WHERE d.file_type = 'PDF'"
        )).fetchall()
        for page_id, width, height, pruned_path in pages:
            scale = page_scale(pruned_path, width, height)
            if scale is None:
                stats["pages_ok"] += 1
                continue
            sx, sy, src_w, src_h = scale
            blocks: List[Tuple[int, list]] = conn.execute(
                text("SELECT id, bbox FROM blocks WHERE page_id = :pid"), {"pid": page_id}
            ).fetchall()
            if not blocks:
                stats["pages_ok"] += 1
                continue
            state = page_state(pruned_path, blocks, sx, sy)
            if state == "fixed":
                stats["pages_skipped_done"] += 1
                continue
            if state == "unknown":
                stats["pages_unknown"] += 1
                continue
            for block_id, bbox in blocks:
                if not bbox or len(bbox) < 4:
                    continue
                new_bbox = [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy]
                if args.apply:
                    conn.execute(
                        text("UPDATE blocks SET bbox = CAST(:bbox AS json) WHERE id = :id"),
                        {"bbox": json.dumps(new_bbox), "id": block_id},
                    )
                stats["blocks_fixed"] += 1
            stats["pages_fixed"] += 1
        if not args.apply:
            conn.rollback()

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"[{mode}] {stats}")


if __name__ == "__main__":
    main()
