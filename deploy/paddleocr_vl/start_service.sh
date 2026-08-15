#!/usr/bin/env bash
# Start the full PaddleOCR-VL pipeline with an ERNIEKit fine-tuned VLM.
set -euo pipefail

PIPELINE_CONFIG="${PADDLEOCR_PIPELINE_CONFIG:-$PWD/pipeline_history.yaml}"
PORT="${PADDLEOCR_PORT:-8888}"

if ! command -v paddlex >/dev/null 2>&1; then
  echo "paddlex not found. Activate the conda environment that contains paddleocr[doc-parser]." >&2
  exit 1
fi

if [[ ! -f "$PIPELINE_CONFIG" ]]; then
  echo "Pipeline config not found: $PIPELINE_CONFIG" >&2
  echo "Run paddlex --get_pipeline_config PaddleOCR-VL, then configure_pipeline.py first." >&2
  exit 1
fi

# The model is local; skip model-hoster probes that can stall on restricted networks.
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

echo "Starting PaddleOCR-VL on port $PORT with $PIPELINE_CONFIG"
exec paddlex --serve --pipeline "$PIPELINE_CONFIG" --port "$PORT"
