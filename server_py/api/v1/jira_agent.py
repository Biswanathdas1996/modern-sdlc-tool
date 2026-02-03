"""API endpoints for JIRA agent."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any

from agents.jira_agent import jira_agent
from core.logging import log_info, log_error
from utils.response import success_response, error_response


router = APIRouter(prefix="/v1/jira-agent", tags=["jira-agent"])


# ==================== REQUEST/RESPONSE MODELS ====================

class SearchJiraRequest(BaseModel):
    """Request model for searching JIRA tickets."""
    prompt: str
    max_results: Optional[int] = 10


class SearchJiraResponse(BaseModel):
    """Response model for JIRA search."""
    success: bool
    prompt: str
    response: str
    intent: Optional[str] = None
    tickets: Optional[List[Any]] = None
    error: Optional[str] = None


class ProcessQueryRequest(BaseModel):
    """Request model for intelligent query processing."""
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


# ==================== API ENDPOINTS ====================

@router.post("/process", response_model=SearchJiraResponse)
async def process_query(request: ProcessQueryRequest):
    """
    Intelligent query processing endpoint.
    
    This endpoint analyzes the user's natural language query and automatically
    determines the appropriate action (search, create, update, or chained operations).
    
    Supported queries:
    - "Find all in-progress tickets" (search)
    - "Create a new bug for login issue" (create)
    - "Update PROJ-123 status to Done" (update)
    - "Find all blocked tickets and mark them as in progress" (chained)
    
    Args:
        request: Query request containing the user prompt
        
    Returns:
        Processed results with tickets and AI analysis
    """
    try:
        log_info(f"JIRA agent query request: {request.prompt}", "jira_agent_api")
        
        result = await jira_agent.process_query(request.prompt)
        
        return SearchJiraResponse(
            success=result.get("success", False),
            prompt=result.get("prompt", ""),
            response=result.get("response", ""),
            intent=result.get("intent"),
            tickets=result.get("tickets", []),
            error=result.get("error")
        )
            
    except Exception as e:
        log_error("Error in JIRA agent query", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process query: {str(e)}"
        )


@router.post("/search", response_model=SearchJiraResponse)
async def search_jira_tickets(request: SearchJiraRequest):
    """
    Search for related JIRA tickets based on a user prompt.
    
    The agent will analyze the prompt and find relevant JIRA tickets
    using semantic search and AI-powered matching.
    
    Args:
        request: Search request containing the user prompt
        
    Returns:
        Search results with related JIRA tickets
    """
    try:
        log_info(f"JIRA agent search request: {request.prompt}", "jira_agent_api")
        
        result = await jira_agent.find_related_tickets(request.prompt)
        
        return SearchJiraResponse(
            success=result.get("success", False),
            prompt=result.get("prompt", ""),
            response=result.get("response", ""),
            intent=result.get("intent"),
            tickets=result.get("tickets", []),
            error=result.get("error")
        )
            
    except Exception as e:
        log_error("Error in JIRA agent search", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search JIRA tickets: {str(e)}"
        )


@router.post("/create", response_model=TicketResponse)
async def create_ticket(request: CreateTicketRequest):
    """
    Create a new JIRA ticket directly.
    
    This endpoint creates a ticket with the specified details without
    going through the AI agent for interpretation.
    
    Args:
        request: Ticket creation request with summary, description, etc.
        
    Returns:
        Created ticket information
    """
    try:
        log_info(f"JIRA create ticket request: {request.summary}", "jira_agent_api")
        
        result = await jira_agent.create_ticket(
            summary=request.summary,
            description=request.description,
            issue_type=request.issue_type,
            priority=request.priority,
            labels=request.labels
        )
        
        return TicketResponse(
            success=result.get("success", False),
            response=result.get("response", ""),
            error=result.get("error") if not result.get("success") else None
        )
            
    except Exception as e:
        log_error("Error creating JIRA ticket", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create JIRA ticket: {str(e)}"
        )


@router.put("/update", response_model=TicketResponse)
async def update_ticket(request: UpdateTicketRequest):
    """
    Update an existing JIRA ticket directly.
    
    This endpoint updates a ticket with the specified changes without
    going through the AI agent for interpretation.
    
    Args:
        request: Ticket update request with ticket_key and fields to update
        
    Returns:
        Update result information
    """
    try:
        log_info(f"JIRA update ticket request: {request.ticket_key}", "jira_agent_api")
        
        result = await jira_agent.update_ticket(
            ticket_key=request.ticket_key,
            summary=request.summary,
            description=request.description,
            status=request.status,
            priority=request.priority,
            comment=request.comment
        )
        
        return TicketResponse(
            success=result.get("success", False),
            response=result.get("response", ""),
            ticket_key=request.ticket_key,
            error=result.get("error") if not result.get("success") else None
        )
            
    except Exception as e:
        log_error("Error updating JIRA ticket", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update JIRA ticket: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint for JIRA agent."""
    return success_response({
        "status": "healthy", 
        "service": "jira-agent",
        "capabilities": ["search", "create", "update", "chained_operations"]
    })
