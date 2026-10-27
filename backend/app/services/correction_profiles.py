"""Bounded, document-scoped context for faithful OCR correction."""

import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.config import settings
from app.core import GPTServiceError

PROMPT_VERSION = "faithful-ocr-v2"


class VerifiedTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=240)
    kind: Literal["person", "place", "organization", "historical_spelling", "other"] = (
        "other"
    )


class CorrectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    languages: list[str] = Field(default_factory=list, max_length=8)
    document_type: Literal["unknown", "handwritten", "printed", "mixed"] = "unknown"
    date_range: str = Field(default="", max_length=80)
    verified_terms: list[VerifiedTerm] = Field(default_factory=list, max_length=30)

    @field_validator("languages")
    @classmethod
    def bounded_languages(cls, values):
        if any(not v.strip() or len(v) > 40 for v in values):
            raise ValueError("Language names must be 1–40 characters")
        return values


def load_document_profile(document_id: int | None) -> CorrectionProfile:
    # A file is read for each new correction request; no cross-volume term cache.
    path = Path(settings.correction_profiles_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    if not path.exists():
        return CorrectionProfile()
    try:
        if path.stat().st_size > 256_000:
            raise ValueError("profile file exceeds 256KB")
        data = json.loads(path.read_text(encoding="utf-8"))
        if set(data) != {"version", "documents"} or data["version"] != 1:
            raise ValueError("expected version=1 and documents")
        profiles = data["documents"]
        if not isinstance(profiles, dict) or any(
            not k.isdigit() or int(k) <= 0 for k in profiles
        ):
            raise ValueError("documents must use positive document IDs")
        # Validate the whole configuration, including profiles not selected now.
        parsed = {k: CorrectionProfile.model_validate(v) for k, v in profiles.items()}
        return parsed.get(str(document_id), CorrectionProfile())
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        raise GPTServiceError(
            f"Invalid correction profile configuration: {type(exc).__name__}"
        ) from exc


def profile_audit(profile: CorrectionProfile) -> dict:
    encoded = json.dumps(profile.model_dump(), ensure_ascii=False, sort_keys=True)
    return {
        "prompt_version": PROMPT_VERSION,
        "profile_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "document_profile": profile.model_dump(),
    }
