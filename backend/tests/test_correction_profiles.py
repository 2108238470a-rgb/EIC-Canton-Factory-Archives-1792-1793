"""Document isolation, active prompt contracts and audit without paid requests."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from app.core import GPTServiceError
from app.services.correction_profiles import (
    CorrectionProfile,
    load_document_profile,
    profile_audit,
)
from app.services.gpt_service import GPTService
from app.schemas import (
    PageCorrectionRequestSchema,
    PageCorrectionBlockInputSchema,
    GPTCompletionResultSchema,
    TokenUsageSchema,
)


class ProfileTests(unittest.TestCase):
    def test_missing_file_is_unknown_not_english(self):
        with patch(
            "app.services.correction_profiles.settings.correction_profiles_path",
            "/tmp/not-a-real-profile-directory/missing.json",
        ):
            self.assertEqual(load_document_profile(58), CorrectionProfile())

    def test_terms_do_not_cross_document_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profiles.json"
            p.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "documents": {
                            "58": {
                                "languages": ["English"],
                                "verified_terms": [
                                    {
                                        "form": "Example",
                                        "source": "Vol A p1",
                                        "kind": "person",
                                    }
                                ],
                            },
                            "61": {"languages": ["Chinese"]},
                        },
                    }
                )
            )
            with patch(
                "app.services.correction_profiles.settings.correction_profiles_path",
                str(p),
            ):
                self.assertEqual(
                    load_document_profile(58).verified_terms[0].form, "Example"
                )
                self.assertEqual(load_document_profile(61).verified_terms, [])
                self.assertEqual(load_document_profile(999), CorrectionProfile())
                p.write_text("{invalid")
                with self.assertRaises(GPTServiceError):
                    load_document_profile(58)

    def test_invalid_or_oversized_profiles_fail_before_generation(self):
        for value in [
            {"languages": ["x" * 41]},
            {"verified_terms": [{"form": "Name", "source": ""}]},
            {"replacement_rules": {"a": "b"}},
        ]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    CorrectionProfile.model_validate(value)

    def test_profile_is_structured_data_in_direct_and_page_calls(self):
        service = GPTService()
        profile = CorrectionProfile(languages=["Chinese"], document_type="printed")
        mock = AsyncMock(
            return_value=GPTCompletionResultSchema(
                text="原文不變", token_usage=TokenUsageSchema(calls=1)
            )
        )
        with patch.object(service, "_request_completion", mock), patch.object(
            service,
            "_load_prompt",
            side_effect=AssertionError("Legacy book prompt must not load"),
        ):
            result = asyncio.run(
                service.process_block_with_usage(
                    "原文不變", ["ocr_correction"], document_profile=profile
                )
            )
        payload = json.loads(mock.await_args.args[1])
        self.assertEqual(payload["document_profile"]["languages"], ["Chinese"])
        self.assertIn("never mandatory replacements", mock.await_args.args[0])
        self.assertEqual(result.quality_report["prompt_version"], "faithful-ocr-v2")
        self.assertEqual(
            result.quality_report["profile_sha256"],
            profile_audit(profile)["profile_sha256"],
        )

        async def echo(system, message, *args, **kwargs):
            payload = json.loads(message)
            self.assertEqual(payload["document_profile"], profile.model_dump())
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
            document_profile=profile,
            blocks=[
                PageCorrectionBlockInputSchema(
                    block_id=i, block_index=i, ocr_text_raw="原文不變" * 300
                )
                for i in range(4)
            ],
        )
        with patch.object(
            service, "_request_completion", AsyncMock(side_effect=echo)
        ) as completion:
            result = asyncio.run(service.correct_ocr_page(request))
        self.assertGreater(completion.await_count, 1)
        self.assertTrue(
            all(
                report["profile_sha256"] == profile_audit(profile)["profile_sha256"]
                for report in result.quality_reports.values()
            )
        )
