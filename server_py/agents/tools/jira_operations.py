"""JIRA API operations for creating and updating tickets."""
import base64
import httpx
from typing import Dict, Any, List, Optional

from core.logging import log_info, log_error


async def create_jira_issue(
    jira_service,
    summary: str,
    description: str,
    issue_type: str = "Story",
    priority: str = "Medium",
    labels: List[str] = None
) -> str:
    """Create a JIRA issue via API.
    
    Args:
        jira_service: JiraService instance
        summary: Ticket summary/title
        description: Ticket description
        issue_type: Issue type (Story, Bug, Task)
        priority: Priority level
        labels: List of labels
        
    Returns:
        Success/failure message
    """
    settings = jira_service.settings
    
    auth = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()
    
    jira_base_url = f"https://{settings.jira_instance_url}/rest/api/3"
    
    # Build description in ADF format
    adf_description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": description or "No description provided"}]
            }
        ]
    }
    
    issue_data = {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "summary": summary,
            "description": adf_description,
            "issuetype": {"name": issue_type},
            "labels": labels or []
        }
    }
    
    # Add priority if supported
    if priority:
        issue_data["fields"]["priority"] = {"name": priority}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{jira_base_url}/issue",
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json=issue_data
        )
        
        if response.status_code == 201:
            data = response.json()
            ticket_key = data.get("key")
            return f"✅ Successfully created ticket **{ticket_key}**: {summary}"
        else:
            error_detail = response.text
            log_error(f"JIRA create error: {error_detail}", "jira_agent")
            return f"❌ Failed to create ticket: {response.status_code} - {error_detail}"


async def update_jira_issue(
    jira_service,
    ticket_key: str,
    fields: Dict[str, Any] = None,
    status: str = None,
    comment: str = None
) -> str:
    """Update a JIRA issue via API.
    
    Args:
        jira_service: JiraService instance
        ticket_key: JIRA ticket key (e.g., PROJ-123)
        fields: Dictionary of fields to update
        status: New status to transition to
        comment: Comment to add
        
    Returns:
        Success/failure message
    """
    settings = jira_service.settings
    
    auth = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()
    
    jira_base_url = f"https://{settings.jira_instance_url}/rest/api/3"
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    results = []
    
    async with httpx.AsyncClient() as client:
        # Update fields if provided
        if fields:
            update_payload = {"fields": {}}
            
            if fields.get('summary'):
                update_payload["fields"]["summary"] = fields['summary']
            
            if fields.get('description'):
                update_payload["fields"]["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": fields['description']}]
                        }
                    ]
                }
            
            if fields.get('priority'):
                update_payload["fields"]["priority"] = {"name": fields['priority']}
            
            if fields.get('labels') is not None:
                update_payload["fields"]["labels"] = fields['labels']
            
            if update_payload["fields"]:
                response = await client.put(
                    f"{jira_base_url}/issue/{ticket_key}",
                    headers=headers,
                    json=update_payload
                )
                
                if response.status_code == 204:
                    results.append("Fields updated")
                else:
                    results.append(f"Field update failed: {response.text}")
        
        # Transition status if provided
        if status:
            # First get available transitions
            trans_response = await client.get(
                f"{jira_base_url}/issue/{ticket_key}/transitions",
                headers=headers
            )
            
            if trans_response.status_code == 200:
                transitions = trans_response.json().get("transitions", [])
                
                # Find matching transition
                target_transition = None
                status_lower = status.lower()
                for t in transitions:
                    if t.get("name", "").lower() == status_lower or \
                       t.get("to", {}).get("name", "").lower() == status_lower:
                        target_transition = t
                        break
                
                if target_transition:
                    trans_payload = {"transition": {"id": target_transition["id"]}}
                    trans_result = await client.post(
                        f"{jira_base_url}/issue/{ticket_key}/transitions",
                        headers=headers,
                        json=trans_payload
                    )
                    
                    if trans_result.status_code == 204:
                        results.append(f"Status changed to '{status}'")
                    else:
                        results.append(f"Status transition failed: {trans_result.text}")
                else:
                    available = [t.get("name") for t in transitions]
                    results.append(f"Status '{status}' not available. Options: {available}")
        
        # Add comment if provided
        if comment:
            comment_payload = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": comment}]
                        }
                    ]
                }
            }
            
            comment_response = await client.post(
                f"{jira_base_url}/issue/{ticket_key}/comment",
                headers=headers,
                json=comment_payload
            )
            
            if comment_response.status_code == 201:
                results.append("Comment added")
            else:
                results.append(f"Comment failed: {comment_response.text}")
    
    if results:
        return f"✅ {ticket_key}: " + ", ".join(results)
    return f"✅ {ticket_key}: No changes requested"


async def get_ticket_details(jira_service, ticket_key: str) -> str:
    """Get detailed information about a specific JIRA ticket.
    
    Args:
        jira_service: JiraService instance
        ticket_key: JIRA ticket key (e.g., PROJ-123)
        
    Returns:
        Formatted ticket details
    """
    ticket_key = ticket_key.strip().upper()
    log_info(f"📋 Getting details for: {ticket_key}", "jira_agent")
    
    # Search for the specific ticket
    tickets = await jira_service.get_jira_stories()
    ticket = next((t for t in tickets if t.get('key') == ticket_key), None)
    
    if not ticket:
        return f"Ticket {ticket_key} not found"
    
    result = f"**{ticket.get('key')}**: {ticket.get('summary')}\n\n"
    result += f"**Status:** {ticket.get('status')}\n"
    result += f"**Priority:** {ticket.get('priority')}\n"
    if ticket.get('labels'):
        result += f"**Labels:** {', '.join(ticket.get('labels', []))}\n"
    if ticket.get('description'):
        result += f"\n**Description:**\n{ticket.get('description')[:500]}..."
    if ticket.get('subtaskCount'):
        result += f"\n**Subtasks:** {ticket.get('subtaskCount')}"
    
    return result
