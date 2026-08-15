"""Custom exceptions for the application."""
from typing import Optional


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, code: str = "APP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class DocumentNotFoundError(AppException):
    """Document not found."""

    def __init__(self, document_id: int):
        super().__init__(
            message=f"Document with id {document_id} not found",
            code="DOCUMENT_NOT_FOUND"
        )


class PageNotFoundError(AppException):
    """Page not found."""

    def __init__(self, page_id: int):
        super().__init__(
            message=f"Page with id {page_id} not found",
            code="PAGE_NOT_FOUND"
        )


class BlockNotFoundError(AppException):
    """Block not found."""

    def __init__(self, block_id: int):
        super().__init__(
            message=f"Block with id {block_id} not found",
            code="BLOCK_NOT_FOUND"
        )


class TaskNotFoundError(AppException):
    """Task not found."""

    def __init__(self, task_id: str):
        super().__init__(
            message=f"Task with id {task_id} not found",
            code="TASK_NOT_FOUND"
        )


class OCRServiceError(AppException):
    """OCR service error."""

    def __init__(self, message: str, detail: Optional[str] = None):
        full_message = f"OCR service error: {message}"
        if detail:
            full_message += f" - {detail}"
        super().__init__(message=full_message, code="OCR_SERVICE_ERROR")


class GPTServiceError(AppException):
    """GPT service error."""

    def __init__(self, message: str, detail: Optional[str] = None):
        full_message = f"GPT service error: {message}"
        if detail:
            full_message += f" - {detail}"
        super().__init__(message=full_message, code="GPT_SERVICE_ERROR")


class FileProcessingError(AppException):
    """File processing error."""

    def __init__(self, message: str):
        super().__init__(message=f"File processing error: {message}", code="FILE_PROCESSING_ERROR")


class ExportError(AppException):
    """Export error."""

    def __init__(self, message: str):
        super().__init__(message=f"Export error: {message}", code="EXPORT_ERROR")
