"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, get_engine
from app.core import logger, AppException
from app.models.research import ALEMBIC_MANAGED_TABLES
from app.services.paddle_service import paddle_service
from app.utils import ensure_directories
from app.api.routers import (
    documents_router,
    pages_router,
    blocks_router,
    tasks_router,
    exports_router,
    kg_router,
    rag_router,
    agent_router,
    research_router,
    groups_router,
)



def _ensure_schema_compatibility() -> None:
    """Apply lightweight schema compatibility fixes for local development."""
    engine = get_engine()
    inspector = inspect(engine)

    if inspector.has_table("documents"):
        columns = {column["name"] for column in inspector.get_columns("documents")}
        if "full_markdown" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE documents ADD COLUMN full_markdown TEXT"))
            logger.info("Added missing documents.full_markdown column")

    if inspector.has_table("blocks"):
        columns = {column["name"] for column in inspector.get_columns("blocks")}
        if "ocr_correction_source_text" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE blocks ADD COLUMN ocr_correction_source_text TEXT")
                )
                connection.execute(
                    text(
                        "UPDATE blocks SET ocr_correction_source_text = ocr_text_raw "
                        "WHERE ocr_text_corrected IS NOT NULL"
                    )
                )
            logger.info("Added and backfilled blocks.ocr_correction_source_text column")


def _startup_tables() -> list:
    """Tables created at startup — everything except the Alembic-managed ones."""
    return [
        table for table in Base.metadata.sorted_tables if table.name not in ALEMBIC_MANAGED_TABLES
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting OCR Platform API...")

    # Create database tables.
    # Tables listed in ALEMBIC_MANAGED_TABLES are deliberately excluded: their
    # DDL must arrive through a reviewed migration, never through an implicit
    # create_all() during application startup.
    engine = get_engine()
    Base.metadata.create_all(bind=engine, tables=_startup_tables())
    _ensure_schema_compatibility()
    logger.info(
        "Database tables created (alembic-managed tables skipped: %s)",
        ", ".join(sorted(ALEMBIC_MANAGED_TABLES)),
    )

    # Ensure storage directories exist
    ensure_directories()
    logger.info("Storage directories initialized")

    yield

    # Shutdown
    logger.info("Shutting down OCR Platform API...")


# Create FastAPI app
app = FastAPI(
    title="OCR Translation Platform",
    description="Platform for OCR processing and translation of historical documents",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle application exceptions."""
    return JSONResponse(
        status_code=400,
        content={"error": {"message": exc.message, "code": exc.code}},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"message": "Internal server error", "code": "INTERNAL_ERROR"}},
    )


# Mount static files for serving images
app.mount("/storage", StaticFiles(directory=settings.storage_path), name="storage")

# Include routers
app.include_router(documents_router, prefix="/api")
app.include_router(pages_router, prefix="/api")
app.include_router(blocks_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(kg_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(groups_router, prefix="/api")



@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": "OCR Translation Platform",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "ocr_model": settings.paddle_ocr_model_name,
        "ocr_endpoint": settings.paddle_ocr_url,
    }


@app.get("/health/ocr")
async def ocr_health_check():
    """Report whether the configured PaddleOCR service is reachable."""
    result = await paddle_service.healthcheck()
    status = "healthy" if result.get("reachable") else "unavailable"
    return {"status": status, **result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
