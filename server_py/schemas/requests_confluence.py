"""Request/response models for Confluence endpoints."""
from pydantic import BaseModel
from typing import Optional


class PublishRequest(BaseModel):
    """Request for publishing BRD to Confluence."""
    brdId: Optional[str] = None
