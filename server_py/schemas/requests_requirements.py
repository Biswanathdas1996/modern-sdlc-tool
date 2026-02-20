"""Request/response models for requirements, BRD, test cases, and user stories endpoints."""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class GenerateUserStoriesRequest(BaseModel):
    """Request for generating user stories."""
    brdId: Optional[str] = None
    brdData: Optional[dict] = None
    documentation: Optional[dict] = None
    parentJiraKey: Optional[str] = None


class UpdateUserStoryRequest(BaseModel):
    """Request for updating a user story."""
    pass


class GenerateBRDRequest(BaseModel):
    """Request for generating BRD."""
    featureRequest: Optional[dict] = None
    analysis: Optional[dict] = None
    databaseSchema: Optional[dict] = None
    documentation: Optional[dict] = None


class GenerateTestCasesRequest(BaseModel):
    """Request for generating test cases."""
    brdId: Optional[str] = None
    brdData: Optional[dict] = None


class GenerateTestDataRequest(BaseModel):
    """Request for generating test data."""
    brdId: Optional[str] = None
    brd: Optional[dict] = None
    documentation: Optional[dict] = None
    testCases: Optional[List[dict]] = None


class GenerateCopilotPromptRequest(BaseModel):
    """Request for generating GitHub Copilot prompt."""
    brd: Optional[dict] = None
    userStories: Optional[List[dict]] = None
    documentation: Optional[dict] = None
    analysis: Optional[dict] = None
    databaseSchema: Optional[dict] = None
    featureRequest: Optional[dict] = None
