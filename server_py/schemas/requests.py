"""Pydantic schemas for API requests and responses."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class InputType(str, Enum):
    """Input type for feature requests."""
    text = "text"
    file = "file"
    audio = "audio"


class RequestType(str, Enum):
    """Type of feature request."""
    feature = "feature"
    bug = "bug"
    change_request = "change_request"


class ProjectStatus(str, Enum):
    """Project analysis status."""
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    error = "error"


class Priority(str, Enum):
    """Priority level."""
    high = "high"
    medium = "medium"
    low = "low"


class BRDStatus(str, Enum):
    """BRD status."""
    draft = "draft"
    review = "review"
    approved = "approved"


# Request schemas
class AnalyzeRequest(BaseModel):
    """Request to analyze a GitHub repository."""
    repoUrl: str = Field(..., description="GitHub repository URL")


class RequirementsRequest(BaseModel):
    """Request to create requirements."""
    title: str
    description: Optional[str] = None
    inputType: InputType
    requestType: RequestType = RequestType.feature


class KnowledgeSearchRequest(BaseModel):
    """Request to search knowledge base."""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=5, ge=1, le=50)
    project_id: Optional[str] = Field(default=None, description="Project ID for scoped search")


class JiraFindRelatedRequest(BaseModel):
    """Request to find related JIRA stories."""
    featureDescription: str


class SyncSubtaskRequest(BaseModel):
    """Request to sync subtask to JIRA."""
    storyId: str
    parentKey: str


class PublishConfluenceRequest(BaseModel):
    """Request to publish BRD to Confluence."""
    brdId: Optional[str] = None


# Jira Agent Interactive Schemas
class MissingInfoField(BaseModel):
    """Field that needs to be collected from user."""
    field: str = Field(..., description="Name of the missing field")
    description: str = Field(..., description="Description of what information is needed")
    options: Optional[List[str]] = Field(default=None, description="Optional list of valid options")


class JiraAgentRequest(BaseModel):
    """Enhanced request model for Jira agent with session support."""
    prompt: str = Field(..., description="User's natural language query")
    session_id: Optional[str] = Field(default=None, description="Session ID for multi-turn conversations")
    context_data: Optional[Dict[str, Any]] = Field(default=None, description="Additional context data from previous turns")
    project_id: Optional[str] = Field(default=None, description="Project ID for project-scoped KB search")


class JiraAgentResponse(BaseModel):
    """Enhanced response model with conversation state."""
    success: bool
    session_id: str
    state: str = Field(..., description="Conversation state: initial, awaiting_info, processing, completed")
    response: str
    
    # Optional fields based on state
    missing_fields: Optional[List[MissingInfoField]] = None
    tickets: Optional[List[Any]] = None
    intent: Optional[str] = None
    error: Optional[str] = None
    
    # Collected data so far
    collected_data: Optional[Dict[str, Any]] = None
