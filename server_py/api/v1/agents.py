"""AI Agents API router for security, unit test, web test, and code generation agents."""
import os
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error
from utils.response import success_response

router = APIRouter(prefix="/v1", tags=["agents"])

# Lazy import agents to avoid circular dependencies and syntax errors
def get_shannon_agent():
    from agents.Shannon_security_agent import shannon_security_agent
    return shannon_security_agent

def get_unit_test_agent():
    try:
        from agents.Unit_test_agent import unit_test_agent
        return unit_test_agent
    except Exception as e:
        log_error("Failed to import unit test agent", "agents", e)
        return None

def get_web_test_agent():
    from agents.Web_test_agent import web_test_agent
    return web_test_agent

def get_code_gen_agent():
    from agents.Code_gen_agent.agent import code_gen_agent
    return code_gen_agent


# ==================== REQUEST/RESPONSE MODELS ====================

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
        
        # Clone repo if needed
        if request.repo_url and not unit_test_agent._get_session(session_id).get("cloned"):
            _clone_repo_for_agent(request.repo_url, session_id, "unit_test_repos", unit_test_agent)
        
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
        
        return _push_to_github(
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
        
        # Clone repo if needed
        if request.repo_url and not code_gen_agent._get_session(session_id).get("cloned"):
            _clone_repo_for_agent(request.repo_url, session_id, "code_gen_repos", code_gen_agent)
        
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
        return _push_to_github(
            agent=code_gen_agent,
            session_id=request.session_id,
            github_token=request.github_token,
            branch_name=request.branch_name or "ai-generated-code",
            commit_message=request.commit_message or "feat: AI-generated code implementation",
            file_patterns=None  # Push all changes
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to push code to GitHub", "agents", e)
        raise internal_error(str(e))


# ==================== HELPER FUNCTIONS ====================

def _clone_repo_for_agent(repo_url: str, session_id: str, base_dir: str, agent):
    """Helper to clone repository for agent use."""
    import subprocess,re as _re, tempfile, shutil
    
    match = _re.match(r'https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$', repo_url)
    if not match:
        return
    
    repo_owner = match.group(1)
    repo_name = match.group(2)
    clone_dir = os.path.join(tempfile.gettempdir(), base_dir, f"{session_id}_{repo_name}")
    
    if not os.path.exists(clone_dir):
        os.makedirs(os.path.dirname(clone_dir), exist_ok=True)
        github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        clone_url = f"https://github.com/{repo_owner}/{repo_name}.git"
        
        if github_token:
            clone_url = f"https://x-access-token:{github_token}@github.com/{repo_owner}/{repo_name}.git"
        
        clone_env = os.environ.copy()
        clone_env["GIT_TERMINAL_PROMPT"] = "0"
        
        try:
            log_info(f"Cloning repo: {repo_owner}/{repo_name}", "agents")
            proc = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, clone_dir],
                capture_output=True,
                text=True,
                timeout=120,
                env=clone_env
            )
            
            if proc.returncode != 0:
                stderr_safe = proc.stderr.replace(github_token, "***") if github_token else proc.stderr
                log_error(f"Git clone failed: {stderr_safe}", "agents")
        except subprocess.TimeoutExpired:
            log_error("Git clone timed out", "agents")
        except Exception as e:
            log_error(f"Git clone error: {type(e).__name__}", "agents")
    
    if os.path.exists(clone_dir) and os.path.isdir(os.path.join(clone_dir, ".git")):
        agent.set_repo(session_id, repo_url, clone_dir, repo_name)
        log_info(f"Repo cloned and linked: {repo_owner}/{repo_name}", "agents")
    elif os.path.exists(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)


def _push_to_github(
    agent: Any,
    session_id: str,
    github_token: str,
    branch_name: str,
    commit_message: str,
    file_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Helper to push agent-generated code to GitHub."""
    import subprocess, re as _re, urllib.parse
    
    session = agent._get_session(session_id)
    if not session.get("cloned") or not session.get("repo_path"):
        raise bad_request("No repository cloned in this session")
    
    repo_path = session["repo_path"]
    repo_url = session.get("repo_url", "")
    
    if not os.path.exists(repo_path):
        raise bad_request("Cloned repository no longer exists")
    
    if not github_token:
        github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not github_token:
        raise bad_request("GitHub token is required")
    
    match = _re.match(r'https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$', repo_url)
    if not match:
        raise bad_request("Invalid repository URL")
    
    repo_owner = match.group(1)
    repo_name = match.group(2)
    push_url = f"https://x-access-token:{github_token}@github.com/{repo_owner}/{repo_name}.git"
    
    push_env = os.environ.copy()
    push_env["GIT_TERMINAL_PROMPT"] = "0"
    
    def run_git(args, cwd=repo_path):
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
            env=push_env
        )
    
    # Configure git
    run_git(["config", "user.email", "docugen-ai@automated.dev"])
    run_git(["config", "user.name", "Defuse 2.O"])
    
    # Get default branch
    default_branch_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    default_branch = default_branch_result.stdout.strip() if default_branch_result.returncode == 0 else "main"
    
    # Create/checkout branch
    checkout_result = run_git(["checkout", "-b", branch_name])
    if checkout_result.returncode != 0:
        run_git(["checkout", branch_name])
    
    # Stage files
    if file_patterns:
        for pattern in file_patterns:
            run_git(["add", "--all", f"**/{pattern}"])
    else:
        run_git(["add", "-A"])
    
    # Check if there are changes
    status_result = run_git(["status", "--porcelain"])
    if not status_result.stdout.strip():
        return {
            "success": True,
            "message": "No changes to push. Everything is up to date."
        }
    
    def sanitize(text: str) -> str:
        if not text or not github_token:
            return text or ""
        return text.replace(github_token, "***").replace(urllib.parse.quote(github_token, safe=""), "***")
    
    # Commit
    commit_result = run_git(["commit", "-m", commit_message])
    if commit_result.returncode != 0:
        raise internal_error(f"Failed to commit: {sanitize(commit_result.stderr)}")
    
    # Push
    push_result = run_git(["push", push_url, branch_name])
    if push_result.returncode != 0:
        stderr_safe = sanitize(push_result.stderr)
        if "already exists" in stderr_safe.lower():
            push_result = run_git(["push", "--force", push_url, branch_name])
            if push_result.returncode != 0:
                raise internal_error(f"Push failed: {sanitize(push_result.stderr)}")
        else:
            raise internal_error(f"Push failed: {stderr_safe}")
    
    changed_files = [
        line.strip().split(maxsplit=1)[-1]
        for line in status_result.stdout.strip().split("\n")
        if line.strip()
    ]
    pr_url = f"https://github.com/{repo_owner}/{repo_name}/compare/{default_branch}...{branch_name}?expand=1"
    
    return {
        "success": True,
        "message": f"Successfully pushed {len(changed_files)} file(s) to branch `{branch_name}`",
        "branch": branch_name,
        "files_pushed": changed_files,
        "pr_url": pr_url,
        "repo_url": repo_url,
    }
