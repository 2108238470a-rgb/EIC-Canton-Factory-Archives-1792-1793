"""Logging configuration."""
import logging
import sys
from typing import Optional

from app.config import settings


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """Setup application logging."""
    log_level = level or ("DEBUG" if settings.debug else "INFO")

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    logger = logging.getLogger("ocr_platform")
    logger.setLevel(log_level)

    return logger


logger = setup_logging()
