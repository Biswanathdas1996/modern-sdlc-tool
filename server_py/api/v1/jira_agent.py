"""Production-ready API endpoints for JIRA agent with rate limiting, validation, and metrics."""
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from agents.jira_agent.jira_agent import jira_agent
from agents.jira_agent.helpers.conversation_manager import conversation_manager
from agents.jira_agent.utils import (
    validate_prompt,
    validate_session_id,
    InputValidationError,
    agent_rate_limiter,
    agent_burst_limiter,
    RateLimitExceeded,
)
from schemas.requests import JiraAgentRequest, JiraAgentResponse, MissingInfoField
from schemas.requests_jira import SearchJiraResponse, ProcessQueryRequest
from core.logging import log_info, log_error, log_warning
from utils.response import success_response


router = APIRouter(prefix="/v1/jira-agent", tags=["jira-agent"])


# ==================== API ENDPOINTS ====================

@router.post("/chat", response_model=JiraAgentResponse)
async def chat_with_agent(request: JiraAgentRequest):
    """
    Interactive chat endpoint with smart information gathering.
    
    Production features:
    - Input validation & sanitization
    - Per-session rate limiting (burst + sustained)
    - Structured error responses with proper HTTP status codes
    - Request duration tracking
    
    Args:
        request: Chat request with prompt and optional session_id
        
    Returns:
        Agent response with conversation state and any requested information
    """
    session_id = None
    try:
        # --- Input validation ---
        validated_prompt = validate_prompt(request.prompt)
        session_id = validate_session_id(request.session_id) or str(uuid.uuid4())

        # --- Rate limiting ---
        rate_key = session_id
        await agent_burst_limiter.check(rate_key)
        await agent_rate_limiter.check(rate_key)
        
        log_info(f"Chat request - Session: {session_id}, Prompt: {validated_prompt[:80]}", "jira_agent_api")
        
        # Get or create conversation context
        conversation_ctx = conversation_manager.get_or_create_context(session_id)
        conversation_ctx.add_message("user", validated_prompt)
        
        # Process with conversation context
        result = await jira_agent.process_query_interactive(
            validated_prompt,
            conversation_ctx=conversation_ctx,
            context_data=request.context_data or {},
            project_id=request.project_id,
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

    except InputValidationError as ve:
        log_warning(f"Validation error: {ve}", "jira_agent_api")
        raise HTTPException(status_code=422, detail=str(ve))

    except RateLimitExceeded as rle:
        log_warning(f"Rate limit exceeded for session {session_id}", "jira_agent_api")
        return JSONResponse(
            status_code=429,
            content={"detail": str(rle), "retry_after": rle.retry_after},
            headers={"Retry-After": str(int(rle.retry_after) + 1)},
        )
            
    except Exception as e:
        log_error("Error in JIRA agent chat", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error processing chat request",
        )


@router.post("/process", response_model=SearchJiraResponse)
async def process_query(request: ProcessQueryRequest):
    """
    Intelligent query processing endpoint (legacy single-turn mode) with validation.
    
    Args:
        request: Query request containing the user prompt
        
    Returns:
        Processed results with tickets and AI analysis
    """
    try:
        validated_prompt = validate_prompt(request.prompt)
        log_info(f"JIRA agent query request: {validated_prompt[:80]}", "jira_agent_api")
        
        result = await jira_agent.process_query(validated_prompt)
        
        return SearchJiraResponse(
            success=result.get("success", False),
            prompt=result.get("prompt", ""),
            response=result.get("response", ""),
            intent=result.get("intent"),
            tickets=result.get("tickets", []),
            error=result.get("error")
        )

    except InputValidationError as ve:
        log_warning(f"Validation error: {ve}", "jira_agent_api")
        raise HTTPException(status_code=422, detail=str(ve))
            
    except Exception as e:
        log_error("Error in JIRA agent query", "jira_agent_api", e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error processing query",
        )



@router.get("/health")
async def health_check():
    """Health check endpoint for JIRA agent with metrics."""
    active_conversations = conversation_manager.get_active_count()
    metrics = jira_agent.get_metrics()
    return success_response({
        "status": "healthy", 
        "service": "jira-agent",
        "capabilities": ["search", "create", "update", "chained_operations", "interactive_chat"],
        "features": {
            "interactive_mode": True,
            "smart_info_gathering": True,
            "multi_turn_conversations": True,
            "active_conversations": active_conversations,
        },
        "metrics": metrics,
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

