"""Annotation gate, unchanged images, leakage checks and portable exports."""

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2] / "ocr_training/scripts"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


prepare = module("prepare_packet")
exporter = module("export_dataset")
builder = module("build_training_config")


class AnnotationToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pilots = []
        for i in range(1, 4):
            image = self.root / f"{i}.png"
            Image.new("RGB", (30, 30), (i * 50, 30, 90)).save(image)
            p = self.root / f"{i}.json"
            p.write_text(
                json.dumps(
                    {
                        "document_id": i,
                        "filename": f"volume{i}.pdf",
                        "pages": [
                            {
                                "image_path": str(image),
                                "pdf_page": 1,
                                "blocks": [
                                    {
                                        "block_id": i,
                                        "bbox": [0, 0, 30, 30],
                                        "raw": "OCR hint",
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
            pilots.append(p)
        self.packet = self.root / "packet"
        prepare.prepare(pilots, self.packet)
        self.rows = exporter.read_csv(self.packet / "annotations.csv")
        self.splits = self.root / "splits.csv"
        self.splits.write_text(
            "split_group,split\nvolume-1,train\nvolume-2,validation\nvolume-3,test\n"
        )

    def save(self):
        with (self.packet / "annotations.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=prepare.COLUMNS)
            w.writeheader()
            w.writerows(self.rows)

    def approve(self):
        for r in self.rows:
            r.update(
                status="approved",
                reference="Original historical spelling.\n£12, 10s.",
                annotator="A",
                reviewer="B",
            )
        self.save()

    def test_blank_packet_is_not_gold_and_approved_export_preserves_text(self):
        ready, counts = exporter.validate(self.packet)
        self.assertEqual(ready, [])
        self.assertEqual(counts["draft"], 3)
        with self.assertRaises(ValueError):
            exporter.export(self.packet, self.splits, self.root / "bad")
        self.approve()
        out = self.root / "export"
        self.assertEqual(
            exporter.export(self.packet, self.splits, out),
            {"train": 1, "validation": 1, "test": 1},
        )
        data = json.loads((out / "train.jsonl").read_text())
        self.assertEqual(data["text_info"][1]["text"], self.rows[0]["reference"])
        self.assertTrue((out / data["image_info"][0]["image_url"]).exists())

    def test_same_reviewer_uncertainty_and_missing_rows_are_rejected(self):
        self.approve()
        self.rows[0]["reviewer"] = "A"
        self.save()
        with self.assertRaises(ValueError):
            exporter.validate(self.packet)
        self.rows[0]["reviewer"] = "B"
        self.rows[0]["uncertainty"] = "name unreadable"
        self.save()
        with self.assertRaises(ValueError):
            exporter.validate(self.packet)
        self.rows.pop()
        self.save()
        with self.assertRaises(ValueError):
            exporter.validate(self.packet)

    def test_image_changes_and_path_escape_are_rejected(self):
        self.rows[0]["image_path"] = "../1.png"
        self.save()
        with self.assertRaises(ValueError):
            exporter.validate(self.packet)
        self.rows[0]["image_path"] = "images/doc1-p1-b1.png"
        self.save()
        Image.new("RGB", (30, 30), "black").save(
            self.packet / self.rows[0]["image_path"]
        )
        with self.assertRaises(ValueError):
            exporter.validate(self.packet)

    def test_volume_and_writer_cannot_cross_partitions(self):
        self.approve()
        self.rows[1]["volume_id"] = self.rows[0]["volume_id"]
        self.save()
        with self.assertRaises(ValueError):
            exporter.export(self.packet, self.splits, self.root / "leak")
        self.rows[1]["volume_id"] = "2"
        self.rows[0]["writer_group"] = self.rows[1]["writer_group"] = "writer-A"
        self.save()
        with self.assertRaises(ValueError):
            exporter.export(self.packet, self.splits, self.root / "writer-leak")


class TrainingConfigTests(unittest.TestCase):
    def test_smoke_config_uses_validation_not_test_and_never_overwrites(self):
        import yaml

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dataset = root / "dataset"
            dataset.mkdir()
            model = root / "model"
            model.mkdir()
            (dataset / "manifest.json").write_text(
                json.dumps({"counts": {"train": 1, "validation": 1, "test": 1}})
            )
            for name in ["train.jsonl", "validation.jsonl"]:
                (dataset / name).write_text("{}\n")
            (model / "config.json").write_text('{"model_type":"paddleocr_vl"}')
            for name in [
                "model.safetensors",
                "preprocessor_config.json",
                "tokenizer_config.json",
                "chat_template.jinja",
            ]:
                (model / name).write_text("test-only-placeholder")
            reference = root / "official.yaml"
            reference.write_text("stage: OCR-VL-SFT\nmax_steps: 926\n")
            output = root / "smoke.yaml"
            builder.build(reference, dataset, model, output)
            config = yaml.safe_load(output.read_text())
            self.assertEqual(config["max_steps"], 10)
            self.assertEqual(config["batch_size"], 1)
            self.assertIn("validation.jsonl", config["eval_dataset_path"])
            self.assertEqual(config["model_name_or_path"], str(model.resolve()))
            with self.assertRaises(ValueError):
                builder.build(reference, dataset, model, output)
