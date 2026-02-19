"""Request/response models for AI agent endpoints."""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class AgentChatRequest(BaseModel):
    """Common chat request for all agents."""
    prompt: str
    session_id: Optional[str] = None
    repo_url: Optional[str] = None
    clear_history: bool = False


class CodeGenRequest(BaseModel):
    """Request for code generation."""
    session_id: str = ""
    repo_url: str = ""
    user_stories: List[Dict[str, Any]]
    copilot_prompt: str
    documentation: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    database_schema: Optional[Dict[str, Any]] = None


class PushToGitHubRequest(BaseModel):
    """Request for pushing to GitHub."""
    session_id: str
    github_token: str = ""
    branch_name: str = "ai-generated-code"
    commit_message: str = "feat: AI-generated code"
