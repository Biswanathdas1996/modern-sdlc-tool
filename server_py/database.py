"""Database operations - backward compatibility wrapper.

This module re-exports from repositories.auth_repository and core.db.postgres
for backward compatibility. New code should import from those modules directly.
"""
from repositories.auth_repository import (
    authenticate_user,
    create_session,
    get_session_user,
    delete_session,
    get_user_permissions,
    create_user,
    get_all_users,
    update_user_permissions,
    update_user_status,
    delete_user,
    update_user_password,
    cleanup_expired_sessions,
    seed_admin_user,
    ALL_FEATURES,
    ALL_FEATURE_KEYS,
)
from core.db.postgres import (
    get_postgres_connection as get_connection,
    init_postgres_database as init_database,
)

__all__ = [
    "get_connection",
    "init_database",
    "authenticate_user",
    "create_session",
    "get_session_user",
    "delete_session",
    "get_user_permissions",
    "create_user",
    "get_all_users",
    "update_user_permissions",
    "update_user_status",
    "delete_user",
    "update_user_password",
    "cleanup_expired_sessions",
    "seed_admin_user",
    "ALL_FEATURES",
    "ALL_FEATURE_KEYS",
]
