#!/usr/bin/env python3
"""Prepare a smoke-test config from a pinned official ERNIEKit reference. Never trains."""
import argparse
import json
from pathlib import Path
import yaml


def build(reference, dataset, model_dir, output, steps=10):
    if output.exists():
        raise ValueError("配置已存在，禁止覆盖")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    if any(
        manifest.get("counts", {}).get(k, 0) < 1
        for k in ["train", "validation", "test"]
    ):
        raise ValueError("需要分组隔离且非空的训练/验证/测试导出")
    for name in ["train.jsonl", "validation.jsonl"]:
        if not (dataset / name).is_file():
            raise ValueError(f"缺少 {name}")
    config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "paddleocr_vl" or not list(
        model_dir.glob("*.safetensors")
    ):
        raise ValueError("不是完整的 PaddleOCR-VL 模型目录；目录完整不代表训练兼容")
    for name in [
        "preprocessor_config.json",
        "tokenizer_config.json",
        "chat_template.jinja",
    ]:
        if not (model_dir / name).is_file():
            raise ValueError(f"模型缺少 {name}")
    data = yaml.safe_load(reference.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("stage") != "OCR-VL-SFT":
        raise ValueError("需要官方 OCR-VL-SFT 配置作为底稿")
    if not 1 <= steps <= 100000:
        raise ValueError("steps 应为正整数且不超过 100000")
    run_dir = output.resolve().parent / (output.stem + "-checkpoints")
    if run_dir.exists():
        raise ValueError("checkpoint 目录已存在，请使用新运行名称")
    data.update(
        model_name_or_path=str(model_dir.resolve()),
        train_dataset_path=str((dataset / "train.jsonl").resolve()),
        eval_dataset_path=str((dataset / "validation.jsonl").resolve()),
        fine_tuning="Full",
        batch_size=1,
        packing_size=1,
        gradient_accumulation_steps=8,
        max_seq_len=4096,
        compute_type="bf16",
        recompute=True,
        learning_rate=5e-6,
        max_steps=steps,
        warmup_steps=min(10, max(1, steps // 100)),
        save_steps=min(10, steps),
        save_total_limit=2,
        output_dir=str(run_dir),
        logging_dir=str(run_dir / "logs"),
    )
    # Official reference's num_samples_each_epoch and optimizer settings remain intact.
    # Max steps controls the smoke run; do not reinterpret it as a full training epoch.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# PROPOSAL ONLY: 1.6 compatibility, processor lengths and GPU fit must pass a smoke test.\n# Run erniekit from the dataset export directory for relative image paths.\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["reference", "dataset", "model-dir", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--steps", type=int, default=10)
    a = p.parse_args()
    try:
        print(build(a.reference, a.dataset, a.model_dir, a.output, a.steps))
    except (ValueError, KeyError, OSError) as e:
        p.exit(1, f"{e}\n")
