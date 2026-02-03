"""Projects API router."""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List
from schemas import Project, AnalyzeRequest
from repositories import storage
from utils.exceptions import not_found, internal_error
from utils.response import success_response
from core.logging import log_info, log_error

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[Project])
async def get_projects():
    """Get all projects."""
    try:
        projects = storage.get_all_projects()
        return [p.model_dump() for p in projects]
    except Exception as e:
        log_error("Error fetching projects", "api", e)
        raise internal_error("Failed to fetch projects")


@router.get("/{id}", response_model=Project)
async def get_project(id: str):
    """Get a specific project."""
    try:
        project = storage.get_project(id)
        if not project:
            raise not_found("Project")
        return project.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error fetching project {id}", "api", e)
        raise internal_error("Failed to fetch project")


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
    background_tasks: BackgroundTasks
):
    """Analyze a GitHub repository."""
    import re
    from ai import analyze_repository, generate_documentation, generate_bpmn_diagram
    
    try:
        repo_url = request.repoUrl
        
        # Validate GitHub URL
        match = re.match(
            r"github\.com/([^/]+)/([^/]+)",
            repo_url.replace("https://", "")
        )
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub URL")
        
        repo_name = f"{match.group(1)}/{match.group(2)}".replace(".git", "")
        
        # Create project
        project = storage.create_project({
            "name": repo_name,
            "repoUrl": repo_url,
            "techStack": [],
            "status": "analyzing",
        })
        
        # Run analysis in background
        async def run_analysis(project_id: str, repo_url: str):
            try:
                # Analyze repository
                analysis = await analyze_repository(repo_url, project_id)
                storage.create_analysis(analysis)
                
                # Update project
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
                
                # Generate documentation
                try:
                    updated_project = storage.get_project(project_id)
                    if updated_project:
                        documentation = await generate_documentation(
                            analysis,
                            updated_project.model_dump()
                        )
                        saved_doc = storage.create_documentation(documentation)
                        
                        # Generate BPMN
                        try:
                            log_info("Generating BPMN diagrams...", "api")
                            bpmn_data = await generate_bpmn_diagram(
                                saved_doc.model_dump(),
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
        
        background_tasks.add_task(run_analysis, project.id, repo_url)
        
        return project.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error analyzing repository", "api", e)
        raise internal_error("Failed to analyze repository")
