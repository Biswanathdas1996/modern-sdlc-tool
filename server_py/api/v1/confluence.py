"""Confluence integration API router for publishing BRDs."""
import os
import json
import base64
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
import httpx

from repositories import storage
from schemas.requests_confluence import PublishRequest
from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error

router = APIRouter(prefix="/confluence", tags=["confluence"])


# ==================== CONFLUENCE ENDPOINTS ====================

@router.post("/publish")
async def publish_to_confluence(request: PublishRequest):
    """
    Publish a BRD to Confluence.
    
    Args:
        request: Optional BRD ID (uses current BRD if not provided)
        
    Returns:
        Published page information with URL
    """
    try:
        # Get Confluence configuration
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        confluence_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
        confluence_space_key = os.environ.get("CONFLUENCE_SPACE_KEY", "~5caf6d452c573b4b24d0f933")
        
        if not jira_email or not jira_token:
            raise bad_request("Confluence credentials not configured.")
        
        # Get BRD
        brd = storage.get_brd(request.brdId) if request.brdId else storage.get_current_brd()
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")
        
        # Prepare authentication
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        confluence_base_url = f"https://{confluence_instance_url}/wiki/api/v2"
        
        # Build Confluence content in Atlas Document Format (ADF)
        adf_content = _build_confluence_content(brd.model_dump())
        
        async with httpx.AsyncClient() as client:
            # Get space ID
            space_response = await client.get(
                f"https://{confluence_instance_url}/wiki/api/v2/spaces",
                params={"keys": confluence_space_key},
                headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
            )
            
            space_id = confluence_space_key
            if space_response.status_code == 200:
                space_data = space_response.json()
                if space_data.get("results"):
                    space_id = space_data["results"][0].get("id", confluence_space_key)
            
            # Create page
            create_page_body = {
                "spaceId": space_id,
                "status": "current",
                "title": f"BRD: {brd.title} - {datetime.now().strftime('%Y-%m-%d')}",
                "body": {
                    "representation": "atlas_doc_format",
                    "value": json.dumps(adf_content)
                }
            }
            
            response = await client.post(
                f"{confluence_base_url}/pages",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                json=create_page_body
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                page_id = data.get("id", "")
                webui_link = data.get("_links", {}).get("webui", "")
                
                if webui_link:
                    page_url = f"https://{confluence_instance_url}/wiki{webui_link}"
                else:
                    page_url = f"https://{confluence_instance_url}/wiki/spaces/{confluence_space_key}/pages/{page_id}"
                
                log_info(f"BRD published to Confluence: {page_url}", "confluence")
                
                return {
                    "success": True,
                    "pageId": page_id,
                    "pageUrl": page_url,
                    "message": "BRD published to Confluence successfully"
                }
            else:
                log_error(f"Confluence API error ({response.status_code}): {response.text}", "confluence")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to publish to Confluence: {response.status_code}"
                )
                
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error publishing to Confluence", "confluence", e)
        raise internal_error("Failed to publish to Confluence")


# ==================== HELPER FUNCTIONS ====================

def _build_confluence_content(brd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build Confluence page content in Atlas Document Format (ADF).
    
    Args:
        brd: BRD dictionary
        
    Returns:
        ADF-formatted content structure
    """
    content = brd.get("content", {})
    
    def create_bullet_list(items: List[str]) -> Dict[str, Any]:
        """Create a bullet list from items."""
        if not items:
            return {
                "type": "paragraph",
                "content": [{"type": "text", "text": "None specified"}]
            }
        
        return {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": item or "N/A"}]
                    }]
                }
                for item in items
            ]
        }
    
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": brd.get("title", "")}]
            },
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Overview"}]
            },
            {
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": content.get("overview", "No overview provided")
                }]
            },
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Objectives"}]
            },
            create_bullet_list(content.get("objectives", [])),
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Scope"}]
            },
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "In Scope"}]
            },
            create_bullet_list(content.get("scope", {}).get("inScope", [])),
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Out of Scope"}]
            },
            create_bullet_list(content.get("scope", {}).get("outOfScope", [])),
            {"type": "rule"},
            {
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": f"Generated by Defuse 2.O | Version: {brd.get('version', '1.0')} | Status: {brd.get('status', 'draft')}",
                    "marks": [{"type": "em"}]
                }]
            }
        ]
    }
