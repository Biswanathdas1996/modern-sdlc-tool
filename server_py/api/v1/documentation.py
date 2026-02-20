"""Documentation, analysis, and BPMN API router."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from repositories import storage
from services import ai_service
from core.logging import log_info, log_error
from utils.exceptions import not_found, internal_error

router = APIRouter(tags=["documentation"])


def _resolve_project_id(project_id: Optional[str] = None) -> str:
    """Resolve project_id: use provided value, or fall back to first project."""
    if project_id:
        project = storage.get_project(project_id)
        if not project:
            raise not_found("Project")
        return project_id
    projects = storage.get_all_projects()
    if not projects:
        raise not_found("No projects found")
    return projects[0]["id"]


@router.get("/analysis/current")
async def get_current_analysis(project_id: Optional[str] = Query(None)):
    """Get the repository analysis for the current or specified project."""
    try:
        pid = _resolve_project_id(project_id)
        analysis = storage.get_analysis(pid)
        if not analysis:
            raise not_found("No analysis found")
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching analysis", "documentation", e)
        raise internal_error("Failed to fetch analysis")


@router.get("/documentation/current")
async def get_current_documentation(project_id: Optional[str] = Query(None)):
    """Get the documentation for the current or specified project."""
    try:
        pid = _resolve_project_id(project_id)
        doc = storage.get_documentation(pid)
        if not doc:
            raise not_found("No documentation found")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching documentation", "documentation", e)
        raise internal_error("Failed to fetch documentation")


@router.get("/bpmn/current")
async def get_current_bpmn(project_id: Optional[str] = Query(None)):
    """Get the BPMN diagrams for the current or specified project."""
    try:
        pid = _resolve_project_id(project_id)
        doc = storage.get_documentation(pid)
        if not doc:
            raise not_found("No documentation found")
        bpmn = storage.get_bpmn_diagram(doc["id"])
        if not bpmn:
            raise not_found("No BPMN diagrams found")
        return bpmn
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching BPMN diagrams", "documentation", e)
        raise internal_error("Failed to fetch BPMN diagrams")


@router.post("/bpmn/regenerate")
async def regenerate_bpmn(project_id: Optional[str] = Query(None)):
    """Regenerate BPMN diagrams from documentation."""
    try:
        pid = _resolve_project_id(project_id)
        project = storage.get_project(pid)
        doc = storage.get_documentation(pid)
        if not doc:
            raise not_found("No documentation found")
        analysis = storage.get_analysis(pid)
        if not analysis:
            raise not_found("No analysis found")
        storage.delete_bpmn_diagram(doc["id"])
        bpmn_data = await ai_service.generate_bpmn_diagram(doc, analysis)
        new_bpmn = storage.create_bpmn_diagram(bpmn_data)
        log_info("BPMN regenerated successfully", "documentation")
        return new_bpmn
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error regenerating BPMN diagram", "documentation", e)
        raise internal_error("Failed to regenerate BPMN diagram")
