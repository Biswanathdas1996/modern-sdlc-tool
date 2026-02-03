"""Custom exceptions for the application."""
from typing import Any, Optional
from fastapi import HTTPException, status


class DocuGenException(Exception):
    """Base exception for DocuGen application."""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class ResourceNotFoundError(DocuGenException):
    """Resource not found exception."""
    pass


class ValidationError(DocuGenException):
    """Validation error exception."""
    pass


class ExternalServiceError(DocuGenException):
    """External service error exception."""
    pass


class DatabaseError(DocuGenException):
    """Database operation error exception."""
    pass


class AIServiceError(DocuGenException):
    """AI service error exception."""
    pass


def http_exception(status_code: int, detail: str) -> HTTPException:
    """Create HTTP exception."""
    return HTTPException(status_code=status_code, detail=detail)


def not_found(resource: str = "Resource") -> HTTPException:
    """Create 404 not found exception."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found"
    )


def bad_request(detail: str) -> HTTPException:
    """Create 400 bad request exception."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail
    )


def internal_error(detail: str = "Internal server error") -> HTTPException:
    """Create 500 internal server error exception."""
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail
    )
