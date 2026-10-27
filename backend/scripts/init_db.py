#!/usr/bin/env python3
"""Database initialization script.

This script ensures:
1. PostgreSQL database exists
2. pgvector extension is enabled
3. All Alembic migrations are applied
"""
import sys
import time
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from alembic.config import Config
from alembic import command

from app.config import settings
from app.core import logger


def wait_for_db(max_retries: int = 30, delay: int = 2) -> bool:
    """Wait for database to be ready."""
    logger.info("Waiting for database to be ready...")

    for attempt in range(max_retries):
        try:
            engine = create_engine(settings.database_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database is ready!")
            return True
        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.info(f"Database not ready (attempt {attempt + 1}/{max_retries}), waiting {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"Database not ready after {max_retries} attempts: {e}")
                return False

    return False


def enable_pgvector() -> bool:
    """Enable pgvector extension."""
    try:
        engine = create_engine(settings.database_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("✓ pgvector extension enabled")
        return True
    except Exception as e:
        logger.error(f"Failed to enable pgvector extension: {e}")
        return False


def run_migrations() -> bool:
    """Run all pending Alembic migrations."""
    try:
        alembic_cfg = Config(str(backend_dir / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        logger.info("✓ All migrations applied successfully")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def main():
    """Main initialization routine."""
    logger.info("=" * 60)
    logger.info("Database Initialization")
    logger.info("=" * 60)

    # Step 1: Wait for database
    if not wait_for_db():
        logger.error("✗ Database connection failed")
        sys.exit(1)

    # Step 2: Enable pgvector
    if not enable_pgvector():
        logger.error("✗ pgvector extension setup failed")
        sys.exit(1)

    # Step 3: Run migrations
    if not run_migrations():
        logger.error("✗ Database migration failed")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("✓ Database initialization completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
