"""JIRA integration API router for syncing stories."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Any

from services import jira_service, ai_service
from repositories import storage
from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error
from utils.response import success_response

router = APIRouter(prefix="/jira", tags=["jira"])


# ==================== REQUEST/RESPONSE MODELS ====================

class FindRelatedRequest(BaseModel):
    """Request for finding related JIRA stories."""
    featureDescription: str


class SyncSubtaskRequest(BaseModel):
    """Request for syncing a user story as a JIRA subtask."""
    storyId: str
    parentKey: str


# ==================== JIRA ENDPOINTS ====================

@router.post("/sync")
async def sync_to_jira():
    """
    Sync user stories to JIRA.
    
    Returns:
        Sync results with created/updated ticket information
    """
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")
        
        user_stories = storage.get_user_stories(brd.id)
        if not user_stories:
            raise bad_request(
                "No user stories found. Please generate user stories first."
            )
        
        result = await jira_service.sync_stories_to_jira(user_stories, storage)
        log_info(f"Synced {len(user_stories)} stories to JIRA", "jira")
        
        return result
        
    except ValueError as ve:
        raise bad_request(str(ve))
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to sync to JIRA", "jira", e)
        raise internal_error("Failed to sync to JIRA")


@router.get("/stories")
async def get_jira_stories_endpoint():
    """
    Get all JIRA stories from the configured project.
    
    Returns:
        List of JIRA stories
    """
    try:
        stories = await jira_service.get_jira_stories()
        return stories
        
    except ValueError as ve:
        raise bad_request(str(ve))
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to fetch JIRA stories", "jira", e)
        raise internal_error("Failed to fetch JIRA stories")


@router.post("/find-related")
async def find_related_jira_stories_endpoint(request: FindRelatedRequest):
    """
    Find related JIRA stories based on feature description.
    
    Args:
        request: Feature description to find related stories
        
    Returns:
        List of related JIRA stories
    """
    try:
        feature_description = request.featureDescription
        
        if not feature_description:
            raise bad_request("Feature description is required")
        
        related_stories = await jira_service.find_related_jira_stories(feature_description)
        
        return {"relatedStories": related_stories}
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to find related stories", "jira", e)
        raise internal_error("Failed to find related stories")


@router.post("/sync-subtask")
async def sync_subtask_to_jira_endpoint(request: SyncSubtaskRequest):
    """
    Sync a user story as a JIRA subtask under a parent story.
    
    Args:
        request: Story ID and parent JIRA key
        
    Returns:
        Created subtask information
    """
    try:
        if not request.storyId or not request.parentKey:
            raise bad_request("Story ID and parent JIRA key are required")
        
        brd = storage.get_current_brd()
        if not brd:
            raise bad_request("No BRD found")
        
        user_stories = storage.get_user_stories(brd.id)
        story = next((s for s in user_stories if s.id == request.storyId), None)
        
        if not story:
            raise HTTPException(status_code=404, detail="User story not found")
        
        result = await jira_service.sync_subtask_to_jira(story, request.parentKey, storage)
        log_info(f"Synced subtask to JIRA under {request.parentKey}", "jira")
        
        return result
        
    except ValueError as ve:
        raise bad_request(str(ve))
    except HTTPException:
        raise
    except Exception as e:
        log_error("Failed to create JIRA subtask", "jira", e)
        raise internal_error("Failed to create JIRA subtask")
