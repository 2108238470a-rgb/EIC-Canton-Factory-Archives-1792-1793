"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.core import logger, AppException
from app.services.paddle_service import paddle_service
from app.utils import ensure_directories
from app.api.routers import (
    documents_router,
    pages_router,
    blocks_router,
    tasks_router,
    exports_router,
)
from app.workbench.api import router as knowledge_router
from app.workbench.compat import router as legacy_router
from app.rag.api import router as rag_router


def _ensure_pgvector_extension() -> None:
    """Ensure pgvector extension is enabled before any table operations."""
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector extension enabled")
    except Exception as e:
        logger.warning(f"Could not enable pgvector extension: {e}")


def _run_migrations() -> None:
    """Run Alembic migrations programmatically."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
    )
    command.upgrade(config, "head")
    logger.info("Database migrations applied successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting OCR Platform API...")

    # Ensure pgvector extension is enabled first
    _ensure_pgvector_extension()

    # Run migrations instead of create_all
    _run_migrations()

    # Apply compatibility fixes
    # All schema changes are managed by Alembic.
    logger.info("Database schema initialized")

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
    logger.exception(
        "Unhandled request error method=%s path=%s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {"message": "Internal server error", "code": "INTERNAL_ERROR"}
        },
    )


# Mount static files for serving images
app.mount("/storage", StaticFiles(directory=settings.storage_path), name="storage")

# Include routers
app.include_router(documents_router, prefix="/api")
app.include_router(pages_router, prefix="/api")
app.include_router(blocks_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api/v2")
app.include_router(rag_router, prefix="/api/v2")
app.include_router(legacy_router, prefix="/api/v2")


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
