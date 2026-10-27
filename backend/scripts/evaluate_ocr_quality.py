"""Evaluate JSONL {id, raw, corrected, reference} with human gold; never call a model."""

import argparse
import json
from pathlib import Path


def distance(a, b):
    if len(a) < len(b):
        a, b = b, a
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        next_row = [i]
        for j, y in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = next_row
    return row[-1]


def evaluate(items):
    rows = []
    for item in items:
        gold = item["reference"]
        raw = item["raw"]
        corrected = item["corrected"]
        if not gold:
            raise ValueError("人工参考文本不能为空")
        before = distance(raw, gold)
        after = distance(corrected, gold)
        words = gold.split()
        rows.append(
            {
                "id": item["id"],
                "reference_chars": len(gold),
                "raw_errors": before,
                "corrected_errors": after,
                "raw_cer": before / len(gold),
                "corrected_cer": after / len(gold),
                "regressed": after > before,
                "reference_words": len(words),
                "raw_word_errors": distance(raw.split(), words),
                "corrected_word_errors": distance(corrected.split(), words),
            }
        )
    if not rows:
        raise ValueError("需要至少一条人工标注记录")
    chars = sum(r["reference_chars"] for r in rows)
    words = sum(r["reference_words"] for r in rows)
    return {
        "units": len(rows),
        "raw_cer": sum(r["raw_errors"] for r in rows) / chars,
        "corrected_cer": sum(r["corrected_errors"] for r in rows) / chars,
        "regression_rate": sum(r["regressed"] for r in rows) / len(rows),
        "improved_units": sum(r["corrected_errors"] < r["raw_errors"] for r in rows),
        "unchanged_units": sum(r["corrected_errors"] == r["raw_errors"] for r in rows),
        "raw_whitespace_wer": sum(r["raw_word_errors"] for r in rows) / max(1, words),
        "corrected_whitespace_wer": sum(r["corrected_word_errors"] for r in rows)
        / max(1, words),
        "note": "CER 按 Unicode 字符计算；WER 按空白分词，中文请以 CER 为主。",
        "items": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        [
            json.loads(line)
            for line in args.input.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"units={result['units']} raw_CER={result['raw_cer']:.4f} corrected_CER={result['corrected_cer']:.4f} regression_rate={result['regression_rate']:.4f}"
    )
