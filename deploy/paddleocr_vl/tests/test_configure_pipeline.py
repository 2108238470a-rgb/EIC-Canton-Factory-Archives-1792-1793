"""Tests for binding an ERNIEKit checkpoint to PaddleX config."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from configure_pipeline import find_named_mapping, main, validate_model_dir


class ConfigurePipelineTests(unittest.TestCase):
    def test_find_nested_vl_recognition(self) -> None:
        node = {"model_name": "PaddleOCR-VL-0.9B"}
        payload = {"SubPipelines": {"doc": {"VLRecognition": node}}}
        self.assertIs(find_named_mapping(payload, "VLRecognition"), node)

    def test_validate_model_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            (model_dir / "config.json").write_text("{}", encoding="utf-8")
            (model_dir / "model.safetensors").touch()
            validate_model_dir(model_dir)

    def test_main_writes_bound_serving_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_dir = root / "model"
            model_dir.mkdir()
            (model_dir / "config.json").write_text("{}", encoding="utf-8")
            (model_dir / "model.safetensors").touch()
            source = root / "source.yaml"
            output = root / "output.yaml"
            source.write_text(
                "SubModules:\n  VLRecognition:\n    model_dir: null\n",
                encoding="utf-8",
            )

            argv = [
                "configure_pipeline.py",
                "--input",
                str(source),
                "--output",
                str(output),
                "--model-dir",
                str(model_dir),
                "--max-pages",
                "25",
            ]
            with patch("sys.argv", argv):
                main()

            payload = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["SubModules"]["VLRecognition"]["model_dir"],
                str(model_dir.resolve()),
            )
            self.assertEqual(payload["SubModules"]["VLRecognition"]["batch_size"], 1)
            self.assertFalse(payload["Serving"]["visualize"])
            self.assertEqual(payload["Serving"]["extra"]["max_num_input_imgs"], 25)


if __name__ == "__main__":
    unittest.main()
