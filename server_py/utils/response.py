"""Response utilities."""
from typing import Any, Optional
from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """Success response model."""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Error response model."""
    success: bool = False
    error: str
    details: Optional[Any] = None


def success_response(data: Any = None, message: Optional[str] = None) -> dict:
    """Create success response."""
    return {"success": True, "data": data, "message": message}


def error_response(error: str, details: Any = None) -> dict:
    """Create error response."""
    return {"success": False, "error": error, "details": details}
