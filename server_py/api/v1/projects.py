"""Projects API router."""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from typing import List
from schemas import AnalyzeRequest
from repositories import storage
from utils.exceptions import not_found, internal_error
from utils.response import success_response
from core.logging import log_info, log_error
from api.v1.auth import get_current_user
from repositories.user_project_repository import get_user_projects, add_user_to_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def get_projects(request: Request):
    """Get all projects. Admins see all, non-admins see only their assigned projects."""
    try:
        user = get_current_user(request)
        if user and user.get("role") != "admin":
            member_projects = get_user_projects(user["id"])
            return member_projects
        projects = storage.get_all_projects()
        return projects
    except Exception as e:
        log_error("Error fetching projects", "api", e)
        raise internal_error("Failed to fetch projects")


@router.post("", status_code=201)
async def create_project(request: dict):
    """Create a new project."""
    try:
        project = storage.create_project({
            "name": request.get("name", ""),
            "repoUrl": request.get("repoUrl", ""),
            "description": request.get("description", ""),
            "techStack": request.get("techStack", []),
            "status": request.get("status", "pending"),
        })
        return project
    except Exception as e:
        log_error("Error creating project", "api", e)
        raise internal_error("Failed to create project")


@router.get("/{id}")
async def get_project(id: str):
    """Get a specific project."""
    try:
        project = storage.get_project(id)
        if not project:
            raise not_found("Project")
        return project
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error fetching project {id}", "api", e)
        raise internal_error("Failed to fetch project")


@router.patch("/{id}")
async def update_project(id: str, request: dict):
    """Update a project."""
    try:
        project = storage.get_project(id)
        if not project:
            raise not_found("Project")
        updates = {}
        for key in ["name", "repoUrl", "description", "status", "techStack"]:
            if key in request:
                updates[key] = request[key]
        updated = storage.update_project(id, updates)
        return updated
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error updating project {id}", "api", e)
        raise internal_error("Failed to update project")


@router.delete("/{id}")
async def delete_project(id: str):
    """Delete a project."""
    try:
        project = storage.get_project(id)
        if not project:
            raise not_found("Project")
        storage.delete_project(id)
        return success_response(message="Project deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error deleting project {id}", "api", e)
        raise internal_error("Failed to delete project")


@router.post("/analyze", status_code=201)
async def analyze_project(
    request: AnalyzeRequest,
    http_request: Request,
    background_tasks: BackgroundTasks
):
    """Analyze a GitHub repository.
    
    If the logged-in user already has an assigned project with the same repo URL,
    re-analyze that project instead of creating a new one.
    New projects are automatically linked to the user.
    """
    import re
    from services import ai_service
    
    try:
        repo_url = request.repoUrl
        
        match = re.match(
            r"github\.com/([^/]+)/([^/]+)",
            repo_url.replace("https://", "")
        )
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub URL")
        
        repo_name = f"{match.group(1)}/{match.group(2)}".replace(".git", "")
        normalized_url = f"https://github.com/{repo_name}"
        
        user = get_current_user(http_request)
        user_id = user["id"] if user else None
        
        existing_project = None
        if user_id:
            user_projects = get_user_projects(user_id)
            for p in user_projects:
                p_url = (p.get("repoUrl") or "").rstrip("/").replace(".git", "")
                if p_url == normalized_url:
                    existing_project = p
                    break
        
        from datetime import datetime
        if existing_project:
            storage.update_project(existing_project["id"], {
                "status": "analyzing",
                "analyzedAt": datetime.utcnow().isoformat(),
            })
            project = storage.get_project(existing_project["id"])
        else:
            project = storage.create_project({
                "name": repo_name,
                "repoUrl": repo_url,
                "techStack": [],
                "status": "analyzing",
                "analyzedAt": datetime.utcnow().isoformat(),
            })
            if user_id:
                add_user_to_project(user_id, project["id"])
        
        async def run_analysis(project_id: str, repo_url: str):
            try:
                analysis = await ai_service.analyze_repository(repo_url, project_id)
                storage.create_analysis(analysis)
                
                tech_stack = []
                if analysis.get("techStack"):
                    tech_stack = (
                        analysis["techStack"].get("languages", []) +
                        analysis["techStack"].get("frameworks", [])
                    )
                
                storage.update_project(project_id, {
                    "techStack": tech_stack,
                    "description": analysis.get("summary", ""),
                })
                
                try:
                    updated_project = storage.get_project(project_id)
                    if updated_project:
                        documentation = await ai_service.generate_documentation(
                            analysis,
                            updated_project
                        )
                        saved_doc = storage.create_documentation(documentation)
                        
                        try:
                            log_info("Generating BPMN diagrams...", "api")
                            bpmn_data = await ai_service.generate_bpmn_diagram(
                                saved_doc,
                                analysis
                            )
                            storage.create_bpmn_diagram(bpmn_data)
                            log_info("BPMN diagrams generated", "api")
                        except Exception as bpmn_error:
                            log_error("BPMN generation failed", "api", bpmn_error)
                except Exception as doc_error:
                    log_error("Documentation generation failed", "api", doc_error)
                
                storage.update_project(project_id, {"status": "completed"})
            except Exception as error:
                log_error("Analysis failed", "api", error)
                storage.update_project(project_id, {"status": "error"})
        
        background_tasks.add_task(run_analysis, project["id"], repo_url)
        
        return project
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error analyzing repository", "api", e)
        raise internal_error("Failed to analyze repository")
