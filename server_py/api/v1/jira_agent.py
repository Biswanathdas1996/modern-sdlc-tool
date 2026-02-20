"""API endpoints for JIRA agent with interactive conversation support."""
import uuid
from fastapi import APIRouter, HTTPException

from agents.jira_agent.jira_agent import jira_agent
from agents.jira_agent.helpers.conversation_manager import conversation_manager
from schemas.requests import JiraAgentRequest, JiraAgentResponse, MissingInfoField
from schemas.requests_jira import SearchJiraResponse, ProcessQueryRequest
from core.logging import log_info, log_error
from utils.response import success_response


router = APIRouter(prefix="/v1/jira-agent", tags=["jira-agent"])


# ==================== API ENDPOINTS ====================

@router.post("/chat", response_model=JiraAgentResponse)
async def chat_with_agent(request: JiraAgentRequest):
    """
    Interactive chat endpoint with smart information gathering.
    
    This endpoint supports multi-turn conversations where the agent can ask
    for missing information and use it to complete tasks.
    
    Features:
    - Automatically detects missing information
    - Asks user for specific details when needed
    - Maintains conversation context across requests
    - Supports all JIRA operations (search, create, update)
    
    Example Flow:
    1. User: "Create a ticket"
       Agent: "ℹ️ I need some additional information: 1. Summary: Please provide a brief title..."
    2. User: "Login button not working"
       Agent: "Please provide a detailed description of the issue"
    3. User: "When clicking login, nothing happens..."
       Agent: "✅ Created ticket PROJ-123: Login button not working"
    
    Args:
        request: Chat request with prompt and optional session_id
        
    Returns:
        Agent response with conversation state and any requested information
    """
    try:
        # Generate or use existing session ID
        session_id = request.session_id or str(uuid.uuid4())
        
        log_info(f"Chat request - Session: {session_id}, Prompt: {request.prompt}", "jira_agent_api")
        
        # Get or create conversation context
        conversation_ctx = conversation_manager.get_or_create_context(session_id)
        conversation_ctx.add_message("user", request.prompt)
        
        # Process with conversation context
        result = await jira_agent.process_query_interactive(
            request.prompt,
            conversation_ctx=conversation_ctx,
            context_data=request.context_data or {}
        )
        
        # Add agent response to conversation
        conversation_ctx.add_message("assistant", result.get("response", ""))
        
        log_info(f"Chat response - Session: {session_id}, State: {result.get('state')}", "jira_agent_api")
        
        return JiraAgentResponse(
            success=result.get("success", False),
            session_id=session_id,
            state=result.get("state", "initial"),
            response=result.get("response", ""),
            missing_fields=[MissingInfoField(**f) for f in result.get("missing_fields", [])],
            tickets=result.get("tickets"),
            intent=result.get("intent"),
            error=result.get("error"),
            collected_data=result.get("collected_data")
        )
            
    except Exception as e:
        log_error("Error in JIRA agent chat", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process chat request: {str(e)}"
        )


@router.post("/process", response_model=SearchJiraResponse)
async def process_query(request: ProcessQueryRequest):
    """
    Intelligent query processing endpoint (legacy single-turn mode).
    
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



@router.get("/health")
async def health_check():
    """Health check endpoint for JIRA agent."""
    active_conversations = conversation_manager.get_active_count()
    return success_response({
        "status": "healthy", 
        "service": "jira-agent",
        "capabilities": ["search", "create", "update", "chained_operations", "interactive_chat"],
        "features": {
            "interactive_mode": True,
            "smart_info_gathering": True,
            "multi_turn_conversations": True,
            "active_conversations": active_conversations
        }
    })


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """
    Get conversation history and context for a session.
    
    Args:
        session_id: The session ID to retrieve
        
    Returns:
        Session information with conversation history and context
    """
    try:
        context = conversation_manager.get_context(session_id)
        
        if not context:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )
        
        return {
            "session_id": session_id,
            "state": context.state.value,
            "summary": context.get_summary(),
            "message_count": len(context.messages),
            "messages": context.messages,
            "collected_data": context.collected_data,
            "created_at": context.created_at.isoformat(),
            "updated_at": context.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error getting session: {session_id}", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get session: {str(e)}"
        )


@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    """
    End a conversation session and clear its context.
    
    Args:
        session_id: The session ID to terminate
        
    Returns:
        Success confirmation
    """
    try:
        conversation_manager.delete_context(session_id)
        log_info(f"Ended session: {session_id}", "jira_agent_api")
        
        return success_response({
            "message": "Session ended successfully",
            "session_id": session_id
        })
    except Exception as e:
        log_error(f"Error ending session: {session_id}", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to end session: {str(e)}"
        )

