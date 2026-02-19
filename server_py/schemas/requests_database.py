"""Request/response models for database schema endpoints."""
from pydantic import BaseModel


class ConnectDatabaseRequest(BaseModel):
    """Request model for database connection."""
    connectionString: str
