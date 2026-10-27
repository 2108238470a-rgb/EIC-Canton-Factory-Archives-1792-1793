"""Historical knowledge module (v2).

This package is a bounded context beside the OCR platform. It stores
corpus metadata, evidence spans, entities, events, and assertions, and
links them back to existing document/page/block IDs without overwriting
OCR text layers.
"""

from app.knowledge import models as knowledge_models

__all__ = ["knowledge_models"]
