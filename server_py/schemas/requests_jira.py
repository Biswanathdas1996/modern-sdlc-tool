"""Request/response models for JIRA endpoints."""
from pydantic import BaseModel
from typing import Optional, List, Any


class FindRelatedRequest(BaseModel):
    """Request for finding related JIRA stories."""
    featureDescription: str


class SyncSubtaskRequest(BaseModel):
    """Request for syncing a user story as a JIRA subtask."""
    storyId: str
    parentKey: str


class SearchJiraRequest(BaseModel):
    """Legacy request model for searching JIRA tickets."""
    prompt: str
    max_results: Optional[int] = 10


class SearchJiraResponse(BaseModel):
    """Legacy response model for JIRA search."""
    success: bool
    prompt: str
    response: str
    intent: Optional[str] = None
    tickets: Optional[List[Any]] = None
    error: Optional[str] = None


class ProcessQueryRequest(BaseModel):
    """Legacy request model for intelligent query processing."""
    prompt: str


class CreateTicketRequest(BaseModel):
    """Request model for creating a JIRA ticket."""
    summary: str
    description: str
    issue_type: Optional[str] = "Story"
    priority: Optional[str] = "Medium"
    labels: Optional[List[str]] = []


class UpdateTicketRequest(BaseModel):
    """Request model for updating a JIRA ticket."""
    ticket_key: str
    summary: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    comment: Optional[str] = None


class TicketResponse(BaseModel):
    """Response model for ticket operations."""
    success: bool
    response: str
    ticket_key: Optional[str] = None
    error: Optional[str] = None
