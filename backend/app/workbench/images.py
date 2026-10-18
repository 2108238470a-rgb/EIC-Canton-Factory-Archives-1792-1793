"""Immutable, content-addressed page images for evidence created from this release."""

import hashlib
import os
import tempfile
from pathlib import Path
from app.config import settings


def freeze_image(page):
    if not page.image_path:
        return None, None
    source = Path(page.image_path).resolve()
    storage = settings.get_storage_path()
    if not source.is_file() or not source.is_relative_to(storage):
        return None, None
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    directory = storage / "results" / "evidence-images"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest + source.suffix.lower())
    if not target.exists():
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
    return str(target), digest
