"""Git operations service for cloning repos and pushing code."""
import os
import re
import subprocess
import shutil
import tempfile
import urllib.parse
from typing import Optional, List, Dict, Any

from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error


GITHUB_REPO_PATTERN = re.compile(
    r'https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$'
)


def parse_github_url(repo_url: str):
    """Parse a GitHub URL into (owner, name) or None."""
    match = GITHUB_REPO_PATTERN.match(repo_url)
    if not match:
        return None
    return match.group(1), match.group(2)


def clone_repo_for_agent(repo_url: str, session_id: str, base_dir: str, agent):
    """Clone a GitHub repository for agent use."""
    parsed = parse_github_url(repo_url)
    if not parsed:
        return

    repo_owner, repo_name = parsed
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
            log_info(f"Cloning repo: {repo_owner}/{repo_name}", "git")
            proc = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, clone_dir],
                capture_output=True,
                text=True,
                timeout=120,
                env=clone_env
            )

            if proc.returncode != 0:
                stderr_safe = proc.stderr.replace(github_token, "***") if github_token else proc.stderr
                log_error(f"Git clone failed: {stderr_safe}", "git")
        except subprocess.TimeoutExpired:
            log_error("Git clone timed out", "git")
        except Exception as e:
            log_error(f"Git clone error: {type(e).__name__}", "git")

    if os.path.exists(clone_dir) and os.path.isdir(os.path.join(clone_dir, ".git")):
        agent.set_repo(session_id, repo_url, clone_dir, repo_name)
        log_info(f"Repo cloned and linked: {repo_owner}/{repo_name}", "git")
    elif os.path.exists(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)


def push_to_github(
    agent: Any,
    session_id: str,
    github_token: str,
    branch_name: str,
    commit_message: str,
    file_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Push agent-generated code to GitHub."""
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

    parsed = parse_github_url(repo_url)
    if not parsed:
        raise bad_request("Invalid repository URL")

    repo_owner, repo_name = parsed
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

    def sanitize(text: str) -> str:
        if not text or not github_token:
            return text or ""
        return text.replace(github_token, "***").replace(
            urllib.parse.quote(github_token, safe=""), "***"
        )

    run_git(["config", "user.email", "docugen-ai@automated.dev"])
    run_git(["config", "user.name", "Defuse 2.O"])

    default_branch_result = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    default_branch = default_branch_result.stdout.strip() if default_branch_result.returncode == 0 else "main"

    checkout_result = run_git(["checkout", "-b", branch_name])
    if checkout_result.returncode != 0:
        run_git(["checkout", branch_name])

    if file_patterns:
        for pattern in file_patterns:
            run_git(["add", "--all", f"**/{pattern}"])
    else:
        run_git(["add", "-A"])

    status_result = run_git(["status", "--porcelain"])
    if not status_result.stdout.strip():
        return {
            "success": True,
            "message": "No changes to push. Everything is up to date."
        }

    commit_result = run_git(["commit", "-m", commit_message])
    if commit_result.returncode != 0:
        raise internal_error(f"Failed to commit: {sanitize(commit_result.stderr)}")

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
