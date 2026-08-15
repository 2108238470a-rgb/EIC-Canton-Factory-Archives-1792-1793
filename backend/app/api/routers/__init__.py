"""API routers module."""
from app.api.routers.documents import router as documents_router
from app.api.routers.pages import router as pages_router
from app.api.routers.blocks import router as blocks_router
from app.api.routers.tasks import router as tasks_router
from app.api.routers.exports import router as exports_router

__all__ = [
    "documents_router",
    "pages_router",
    "blocks_router",
    "tasks_router",
    "exports_router",
]
