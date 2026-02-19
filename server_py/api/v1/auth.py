"""Authentication and authorization API router."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from database import (
    authenticate_user, create_session, get_session_user,
    delete_session, get_user_permissions, create_user, get_all_users,
    update_user_permissions, update_user_status, delete_user as db_delete_user,
    update_user_password, ALL_FEATURES, ALL_FEATURE_KEYS
)
from core.logging import log_info, log_error
from utils.exceptions import bad_request, not_found, internal_error
from utils.response import success_response

router = APIRouter(tags=["auth"])

SESSION_COOKIE = "docugen_session"


# ==================== DEPENDENCIES ====================

def get_current_user(request: Request) -> Optional[dict]:
    """Get the currently authenticated user from session cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    return get_session_user(session_id)


def require_auth(request: Request) -> dict:
    """Require authentication for endpoint."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(request: Request) -> dict:
    """Require admin role for endpoint."""
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_feature(request: Request, feature_key: str) -> dict:
    """Require specific feature permission for endpoint."""
    user = require_auth(request)
    if user["role"] == "admin":
        return user
    permissions = get_user_permissions(user["id"])
    if feature_key not in permissions:
        raise HTTPException(
            status_code=403,
            detail=f"Access to {feature_key} is not granted"
        )
    return user


# ==================== REQUEST/RESPONSE MODELS ====================

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


# ==================== AUTH ENDPOINTS ====================

@router.post("/auth/login")
async def login(request: LoginRequest, raw_request: Request):
    """
    Authenticate user and create session.
    
    Args:
        request: Login credentials
        raw_request: Raw FastAPI request for cookie management
        
    Returns:
        User information and permissions with session cookie
    """
    try:
        email = request.email.strip()
        password = request.password
        
        if not email or not password:
            raise bad_request("Email and password are required")
        
        user = authenticate_user(email, password)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        session_id = create_session(user["id"])
        permissions = get_user_permissions(user["id"])
        
        response = JSONResponse(content={
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            },
            "permissions": permissions,
        })
        
        response.set_cookie(
            key=SESSION_COOKIE,
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=86400,  # 24 hours
            path="/",
        )
        
        log_info(f"User logged in: {email}", "auth")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Login failed", "auth", e)
        raise internal_error("Login failed")


@router.post("/auth/logout")
async def logout(request: Request):
    """
    Logout user and delete session.
    
    Args:
        request: FastAPI request with session cookie
        
    Returns:
        Success response with cleared session cookie
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        delete_session(session_id)
    
    response = JSONResponse(content={"success": True})
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    
    log_info("User logged out", "auth")
    return response


@router.get("/auth/me")
async def get_me(request: Request):
    """
    Get current authenticated user information.
    
    Args:
        request: FastAPI request with session cookie
        
    Returns:
        Current user information and permissions
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    permissions = get_user_permissions(user["id"])
    
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        },
        "permissions": permissions,
    }


@router.get("/auth/features")
async def get_features():
    """
    Get all available features in the application.
    
    Returns:
        List of all feature definitions
    """
    return ALL_FEATURES


# ==================== ADMIN ENDPOINTS ====================

@router.get("/admin/users")
async def admin_get_users(request: Request):
    """
    Get all users (admin only).
    
    Args:
        request: FastAPI request with admin session
        
    Returns:
        List of all users
    """
    require_admin(request)
    return get_all_users()


@router.post("/admin/users")
async def admin_create_user(user_data: CreateUserRequest, request: Request):
    """
    Create a new user (admin only).
    
    Args:
        user_data: User creation data
        request: FastAPI request with admin session
        
    Returns:
        Created user information
    """
    require_admin(request)
    
    try:
        username = user_data.username.strip()
        email = user_data.email.strip()
        password = user_data.password
        role = user_data.role
        features = user_data.features
        
        if not username or not email or not password:
            raise bad_request("Username, email, and password are required")
        
        if role not in ("admin", "user"):
            raise bad_request("Role must be admin or user")
        
        user = create_user(username, email, password, role, features)
        log_info(f"User created: {email}", "admin")
        
        return user
        
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to create user", "admin", e)
        raise internal_error("Failed to create user")


@router.patch("/admin/users/{user_id}/permissions")
async def admin_update_permissions(
    user_id: str,
    permissions_data: UpdatePermissionsRequest,
    request: Request
):
    """
    Update user permissions (admin only).
    
    Args:
        user_id: User ID to update
        permissions_data: New permissions list
        request: FastAPI request with admin session
        
    Returns:
        Updated user information
    """
    require_admin(request)
    
    try:
        features = permissions_data.features
        valid_features = [f for f in features if f in ALL_FEATURE_KEYS]
        
        user = update_user_permissions(user_id, valid_features)
        log_info(f"Updated permissions for user: {user_id}", "admin")
        
        return user
        
    except Exception as e:
        log_error("Failed to update permissions", "admin", e)
        raise internal_error("Failed to update permissions")


@router.patch("/admin/users/{user_id}/status")
async def admin_update_status(
    user_id: str,
    status_data: UpdateStatusRequest,
    request: Request
):
    """
    Update user active status (admin only).
    
    Args:
        user_id: User ID to update
        status_data: New status
        request: FastAPI request with admin session
        
    Returns:
        Updated user information
    """
    require_admin(request)
    
    try:
        is_active = status_data.is_active
        user = update_user_status(user_id, is_active)
        
        log_info(f"Updated status for user: {user_id} to {is_active}", "admin")
        return user
        
    except ValueError as ve:
        raise bad_request(str(ve))
    except Exception as e:
        log_error("Failed to update user status", "admin", e)
        raise internal_error("Failed to update user status")


@router.patch("/admin/users/{user_id}/password")
async def admin_reset_password(
    user_id: str,
    password_data: UpdatePasswordRequest,
    request: Request
):
    """
    Reset user password (admin only).
    
    Args:
        user_id: User ID to update
        password_data: New password
        request: FastAPI request with admin session
        
    Returns:
        Success confirmation
    """
    require_admin(request)
    
    try:
        new_password = password_data.password
        
        if not new_password or len(new_password) < 6:
            raise bad_request("Password must be at least 6 characters")
        
        update_user_password(user_id, new_password)
        log_info(f"Password reset for user: {user_id}", "admin")
        
        return success_response(message="Password reset successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to reset password", "admin", e)
        raise internal_error("Failed to reset password")


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request):
    """
    Delete a user (admin only).
    
    Args:
        user_id: User ID to delete
        request: FastAPI request with admin session
        
    Returns:
        Success confirmation
    """
    require_admin(request)
    
    try:
        db_delete_user(user_id)
        log_info(f"User deleted: {user_id}", "admin")
        
        return success_response(message="User deleted successfully")
        
    except ValueError as ve:
        raise bad_request(str(ve))
    except Exception as e:
        log_error("Failed to delete user", "admin", e)
        raise internal_error("Failed to delete user")
