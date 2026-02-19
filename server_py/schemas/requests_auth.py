"""Request/response models for authentication endpoints."""
from pydantic import BaseModel
from typing import List


class LoginRequest(BaseModel):
    """Login request model."""
    email: str
    password: str


class CreateUserRequest(BaseModel):
    """Create user request model."""
    username: str
    email: str
    password: str
    role: str = "user"
    features: List[str] = []


class UpdatePermissionsRequest(BaseModel):
    """Update permissions request model."""
    features: List[str]


class UpdateStatusRequest(BaseModel):
    """Update user status request model."""
    is_active: bool = True


class UpdatePasswordRequest(BaseModel):
    """Update password request model."""
    password: str
