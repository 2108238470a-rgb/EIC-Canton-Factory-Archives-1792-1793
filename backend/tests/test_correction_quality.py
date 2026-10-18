import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
from app.services.correction_quality import (
    assess_correction,
    ocr_warnings,
    FAITHFUL_PROMPT,
)
from app.services.gpt_service import GPTService
from app.schemas import (
    GPTCompletionResultSchema,
    TokenUsageSchema,
    PageCorrectionRequestSchema,
    PageCorrectionBlockInputSchema,
)


class CorrectionQualityTests(unittest.TestCase):
    def test_no_change_is_valid(self):
        raw = "Mr. Leach paid 1792 taels, not 1793.\n廣州 publick service."
        self.assertTrue(assess_correction(raw, raw)["accepted"])

    def test_local_ocr_repair_can_pass(self):
        self.assertEqual(
            assess_correction("tender more regular", "render more regular")["text"],
            "render more regular",
        )

    def test_similar_names_are_not_silently_normalized(self):
        r = assess_correction(
            "Mr. Leach sent the letter.", "Mr. Peach sent the letter."
        )
        self.assertFalse(r["accepted"])
        self.assertIn("names_or_capitals_changed", r["reasons"])
        self.assertIn("Peach", r["candidate"])
        self.assertIn("Leach", r["text"])

    def test_numeric_multiplicity_is_preserved(self):
        self.assertFalse(
            assess_correction("Paid 12 and 12 taels.", "Paid 12 taels.")["accepted"]
        )

    def test_negation_script_and_historical_forms_are_protected(self):
        for raw, candidate in [
            ("not sent", "sent"),
            ("廣州來函", "letter"),
            ("publick service", "public service"),
        ]:
            with self.subTest(raw=raw):
                self.assertFalse(assess_correction(raw, candidate)["accepted"])

    def test_unicode_change_offsets_slice_original(self):
        r = assess_correction("😀 tender more regular", "😀 render more regular")
        c = r["changes"][0]
        self.assertEqual("😀 tender more regular"[c["start"] : c["end"]], c["before"])

    def test_large_rewrite_cannot_pass(self):
        self.assertFalse(
            assess_correction(
                "The letter was sent to Canton.",
                "A historical account describes several new events and people.",
            )["accepted"]
        )

    def test_repeat_warning_is_not_a_quality_score(self):
        self.assertIn("repeated_generation", ocr_warnings("abcdefgh" * 6))

    def test_model_guard_applies_to_direct_and_page_entry(self):
        service = GPTService()
        with patch.object(
            service,
            "_request_completion",
            new=AsyncMock(
                return_value=GPTCompletionResultSchema(
                    text="Mr. Peach sent the letter.",
                    token_usage=TokenUsageSchema(calls=1),
                )
            ),
        ):
            self.assertEqual(
                asyncio.run(service.correct_ocr("Mr. Leach sent the letter.")),
                "Mr. Leach sent the letter.",
            )
        request = PageCorrectionRequestSchema(
            page_number=1,
            blocks=[
                PageCorrectionBlockInputSchema(
                    block_id=1, block_index=0, ocr_text_raw="Mr. Leach sent the letter."
                )
            ],
        )
        mock = AsyncMock(
            return_value=GPTCompletionResultSchema(
                text='{"blocks":[{"block_id":1,"ocr_text_corrected":"Mr. Peach sent the letter."}]}',
                token_usage=TokenUsageSchema(calls=1),
            )
        )
        with patch.object(service, "_request_completion", new=mock):
            result = asyncio.run(service.correct_ocr_page(request))
        self.assertFalse(result.quality_reports[1]["accepted"])
        self.assertEqual(
            result.blocks[0].ocr_text_corrected, "Mr. Leach sent the letter."
        )
        self.assertEqual(mock.await_args.args[0], FAITHFUL_PROMPT)

    def test_dense_pages_are_budgeted_without_losing_or_duplicating_blocks(self):
        service = GPTService()

        async def completion(system, message, mode, **kwargs):
            import json

            payload = json.loads(message)
            self.assertLessEqual(
                sum(len(b["ocr_text_raw"]) for b in payload["blocks"]), 3500
            )
            return GPTCompletionResultSchema(
                text=json.dumps(
                    {
                        "blocks": [
                            {
                                "block_id": b["block_id"],
                                "ocr_text_corrected": b["ocr_text_raw"],
                            }
                            for b in payload["blocks"]
                        ]
                    }
                ),
                token_usage=TokenUsageSchema(calls=1),
            )

        request = PageCorrectionRequestSchema(
            page_number=1,
            blocks=[
                PageCorrectionBlockInputSchema(
                    block_id=i, block_index=i, ocr_text_raw="unchanged passage " * 60
                )
                for i in range(8)
            ],
        )
        mock = AsyncMock(side_effect=completion)
        with patch.object(service, "_request_completion", new=mock):
            result = asyncio.run(service.correct_ocr_page(request))
        self.assertGreater(mock.await_count, 1)
        self.assertEqual([b.block_id for b in result.blocks], list(range(8)))
        self.assertEqual(result.token_usage.calls, mock.await_count)

    def test_gold_evaluation_exposes_per_unit_regression(self):
        path = Path(__file__).resolve().parents[1] / "scripts/evaluate_ocr_quality.py"
        spec = importlib.util.spec_from_file_location("quality_eval", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        r = module.evaluate(
            [
                {"id": 1, "raw": "wxyz", "corrected": "abcd", "reference": "abcd"},
                {"id": 2, "raw": "abcd", "corrected": "abxcd", "reference": "abcd"},
            ]
        )
        self.assertLess(r["corrected_cer"], r["raw_cer"])
        self.assertEqual(r["regression_rate"], 0.5)
