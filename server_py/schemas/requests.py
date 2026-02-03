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
