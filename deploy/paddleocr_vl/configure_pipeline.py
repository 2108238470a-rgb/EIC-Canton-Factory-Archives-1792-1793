#!/usr/bin/env python3
"""Bind an ERNIEKit PaddleOCR-VL checkpoint to a generated pipeline config."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def find_named_mapping(value: Any, name: str) -> dict[str, Any] | None:
    """Find the first nested mapping stored under *name*."""
    if not isinstance(value, dict):
        return None
    candidate = value.get(name)
    if isinstance(candidate, dict):
        return candidate
    for child in value.values():
        found = find_named_mapping(child, name)
        if found is not None:
            return found
    return None


def validate_model_dir(model_dir: Path) -> None:
    required = [model_dir / "config.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if not list(model_dir.glob("*.safetensors")):
        missing.append(str(model_dir / "*.safetensors"))
    if missing:
        raise SystemExit("ERNIEKit model directory is incomplete: " + ", ".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args()

    model_dir = args.model_dir.expanduser().resolve()
    validate_model_dir(model_dir)
    payload = yaml.safe_load(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Pipeline config must contain a YAML mapping")

    vl_recognition = find_named_mapping(payload, "VLRecognition")
    if vl_recognition is None:
        raise SystemExit("Could not find VLRecognition in the generated pipeline config")
    if vl_recognition.get("genai_config"):
        raise SystemExit(
            "This config delegates recognition to a separate GenAI server. "
            "Generate the local PaddleOCR-VL config on the target server before binding model_dir."
        )

    vl_recognition["model_dir"] = str(model_dir)
    vl_recognition["batch_size"] = 1

    serving = payload.setdefault("Serving", {})
    if not isinstance(serving, dict):
        raise SystemExit("Serving must be a YAML mapping")
    serving["visualize"] = False
    extra = serving.setdefault("extra", {})
    if not isinstance(extra, dict):
        raise SystemExit("Serving.extra must be a YAML mapping")
    extra["max_num_input_imgs"] = args.max_pages

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    print(f"VLRecognition.model_dir={model_dir}")
    print(f"Serving.extra.max_num_input_imgs={args.max_pages}")


if __name__ == "__main__":
    main()
