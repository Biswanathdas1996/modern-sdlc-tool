"""AI Agents API router for security, unit test, web test, and code generation agents."""
import uuid
from fastapi import APIRouter, HTTPException

from schemas.requests_agents import AgentChatRequest, CodeGenRequest, PushToGitHubRequest
from services.git_service import clone_repo_for_agent, push_to_github
from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error

router = APIRouter(prefix="/v1", tags=["agents"])


def get_shannon_agent():
    from agents.shannon_security_agent import shannon_security_agent
    return shannon_security_agent

def get_unit_test_agent():
    try:
        from agents.unit_test_agent import unit_test_agent
        return unit_test_agent
    except Exception as e:
        log_error("Failed to import unit test agent", "agents", e)
        return None

def get_web_test_agent():
    from agents.web_test_agent import web_test_agent
    return web_test_agent

def get_code_gen_agent():
    from agents.code_gen_agent.agent import code_gen_agent
    return code_gen_agent


# ==================== SECURITY AGENT ====================

@router.post("/security-agent/chat")
async def chat_with_security_agent(request: AgentChatRequest):
    """Chat with Shannon security analysis agent."""
    try:
        if not request.prompt:
            raise bad_request("Prompt is required")

        session_id = request.session_id or "default"
        shannon_agent = get_shannon_agent()
        result = shannon_agent.process_query(request.prompt, session_id)

        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "thinking_steps": result.get("thinking_steps", []),
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Security agent chat failed", "agents", e)
        raise internal_error(f"Failed to process security agent request: {str(e)}")


# ==================== UNIT TEST AGENT ====================

@router.post("/unit-test-agent/chat")
async def chat_with_unit_test_agent(request: AgentChatRequest):
    """Chat with unit test generation agent."""
    try:
        if not request.prompt:
            raise bad_request("Prompt is required")

        session_id = request.session_id or "default"

        unit_test_agent = get_unit_test_agent()
        if not unit_test_agent:
            raise internal_error("Unit test agent is not available")

        if request.repo_url and not unit_test_agent._get_session(session_id).get("cloned"):
            clone_repo_for_agent(request.repo_url, session_id, "unit_test_repos", unit_test_agent)

        result = unit_test_agent.process_query(request.prompt, session_id)

        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "thinking_steps": result.get("thinking_steps", []),
            "task_id": result.get("task_id"),
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Unit test agent chat failed", "agents", e)
        raise internal_error(f"Failed to process unit test agent request: {str(e)}")


@router.get("/unit-test-agent/task/{task_id}")
async def get_unit_test_task_status(task_id: str):
    """Get unit test generation task status."""
    try:
        unit_test_agent = get_unit_test_agent()
        if not unit_test_agent:
            raise HTTPException(status_code=503, detail="Unit test agent not available")

        task = unit_test_agent.tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return {
            "task_id": task_id,
            "status": task.get("status", "unknown"),
            "progress": task.get("progress", ""),
            "response": task.get("response"),
            "success": task.get("success"),
            "thinking_steps": task.get("thinking_steps", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to get task status", "agents", e)
        raise internal_error(str(e))


@router.post("/unit-test-agent/push-to-github")
async def push_tests_to_github(request: PushToGitHubRequest):
    """Push generated unit tests to GitHub."""
    try:
        unit_test_agent = get_unit_test_agent()
        if not unit_test_agent:
            raise internal_error("Unit test agent is not available")

        return push_to_github(
            agent=unit_test_agent,
            session_id=request.session_id,
            github_token=request.github_token,
            branch_name=request.branch_name or "ai-generated-tests",
            commit_message=request.commit_message or "feat: add AI-generated unit tests",
            file_patterns=["*test*", "*spec*", "*__tests__*"]
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to push tests to GitHub", "agents", e)
        raise internal_error(str(e))


# ==================== WEB TEST AGENT ====================

@router.post("/web-test-agent/chat")
async def chat_with_web_test_agent(request: AgentChatRequest):
    """Chat with web test generation agent."""
    try:
        if not request.prompt:
            raise bad_request("Prompt is required")

        session_id = request.session_id or "default"
        web_test_agent = get_web_test_agent()
        result = web_test_agent.process_query(
            request.prompt,
            session_id,
            request.clear_history
        )

        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "thinking_steps": result.get("thinking_steps", []),
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Web test agent chat failed", "agents", e)
        raise internal_error(f"Failed to process web test agent request: {str(e)}")


# ==================== CODE GENERATION AGENT ====================

@router.post("/code-gen/generate")
async def start_code_generation(request: CodeGenRequest):
    """Start code generation task."""
    try:
        if not request.user_stories:
            raise bad_request("User stories are required")
        if not request.copilot_prompt:
            raise bad_request("Copilot prompt is required")

        session_id = request.session_id or str(uuid.uuid4())
        code_gen_agent = get_code_gen_agent()

        if request.repo_url and not code_gen_agent._get_session(session_id).get("cloned"):
            clone_repo_for_agent(request.repo_url, session_id, "code_gen_repos", code_gen_agent)

        result = code_gen_agent.start_generation(
            session_id,
            request.user_stories,
            request.copilot_prompt,
            request.documentation,
            request.analysis,
            request.database_schema
        )

        return {
            "success": result.get("success", False),
            "task_id": result.get("task_id"),
            "error": result.get("error"),
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Code generation failed", "agents", e)
        raise internal_error(f"Failed to start code generation: {str(e)}")


@router.get("/code-gen/task/{task_id}")
async def get_code_gen_task_status(task_id: str):
    """Get code generation task status."""
    try:
        code_gen_agent = get_code_gen_agent()
        status = code_gen_agent.get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail="Task not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to get code gen task status", "agents", e)
        raise internal_error(str(e))


@router.post("/code-gen/push-to-github")
async def push_generated_code_to_github(request: PushToGitHubRequest):
    """Push generated code to GitHub."""
    try:
        code_gen_agent = get_code_gen_agent()
        return push_to_github(
            agent=code_gen_agent,
            session_id=request.session_id,
            github_token=request.github_token,
            branch_name=request.branch_name or "ai-generated-code",
            commit_message=request.commit_message or "feat: AI-generated code implementation",
            file_patterns=None
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to push code to GitHub", "agents", e)
        raise internal_error(str(e))
