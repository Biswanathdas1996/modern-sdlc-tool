"""Documentation, analysis, and BPMN API router."""
from fastapi import APIRouter, HTTPException
from repositories import storage
from services import ai_service
from core.logging import log_info, log_error
from utils.exceptions import not_found, internal_error

router = APIRouter(tags=["documentation"])


@router.get("/analysis/current")
async def get_current_analysis():
    """Get the current repository analysis."""
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise not_found("No projects found")
        
        analysis = storage.get_analysis(projects[0].id)
        if not analysis:
            raise not_found("No analysis found")
        
        return analysis.model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching analysis", "documentation", e)
        raise internal_error("Failed to fetch analysis")


@router.get("/documentation/current")
async def get_current_documentation():
    """Get the current project documentation."""
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise not_found("No projects found")
        
        doc = storage.get_documentation(projects[0].id)
        if not doc:
            raise not_found("No documentation found")
        
        return doc.model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching documentation", "documentation", e)
        raise internal_error("Failed to fetch documentation")


@router.get("/bpmn/current")
async def get_current_bpmn():
    """Get the current BPMN diagrams."""
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise not_found("No projects found")
        
        doc = storage.get_documentation(projects[0].id)
        if not doc:
            raise not_found("No documentation found")
        
        bpmn = storage.get_bpmn_diagram(doc.id)
        if not bpmn:
            raise not_found("No BPMN diagrams found")
        
        return bpmn.model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching BPMN diagrams", "documentation", e)
        raise internal_error("Failed to fetch BPMN diagrams")


@router.post("/bpmn/regenerate")
async def regenerate_bpmn():
    """Regenerate BPMN diagrams from documentation."""
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise not_found("No projects found")
        
        project = projects[0]
        doc = storage.get_documentation(project.id)
        if not doc:
            raise not_found("No documentation found")
        
        analysis = storage.get_analysis(project.id)
        if not analysis:
            raise not_found("No analysis found")
        
        # Delete existing and generate new
        storage.delete_bpmn_diagram(doc.id)
        bpmn_data = await ai_service.generate_bpmn_diagram(doc.model_dump(), analysis.model_dump())
        new_bpmn = storage.create_bpmn_diagram(bpmn_data)
        
        log_info("BPMN regenerated successfully", "documentation")
        return new_bpmn.model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error regenerating BPMN diagram", "documentation", e)
        raise internal_error("Failed to regenerate BPMN diagram")
