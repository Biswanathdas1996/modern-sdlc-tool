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
        description: Ticket description (supports markdown)
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
    
    # Build description in ADF format from markdown
    adf_description = markdown_to_adf(description)
    
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
                update_payload["fields"]["description"] = markdown_to_adf(fields['description'])
            
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


def markdown_to_adf(markdown_text: str) -> Dict[str, Any]:
    """Convert markdown text to Atlassian Document Format (ADF).
    
    Supports: headers, bullet lists, bold, code blocks, paragraphs.
    """
    if not markdown_text:
        return {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "No description provided"}]}]
        }
    
    content = []
    lines = markdown_text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Skip empty lines
        if not line.strip():
            i += 1
            continue
        
        # Headers
        if line.startswith('### '):
            content.append({
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": line[4:].strip()}]
            })
            i += 1
            continue
        elif line.startswith('## '):
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": line[3:].strip()}]
            })
            i += 1
            continue
        elif line.startswith('# '):
            content.append({
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": line[2:].strip()}]
            })
            i += 1
            continue
        
        # Bullet list
        if line.strip().startswith('- ') or line.strip().startswith('* '):
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                item_text = lines[i].strip()[2:].strip()
                list_items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": item_text}]
                    }]
                })
                i += 1
            content.append({
                "type": "bulletList",
                "content": list_items
            })
            continue
        
        # Code block
        if line.strip().startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # Skip closing ```
            content.append({
                "type": "codeBlock",
                "content": [{"type": "text", "text": '\n'.join(code_lines)}]
            })
            continue
        
        # Regular paragraph - handle bold and inline formatting
        text_content = []
        remaining = line
        
        while remaining:
            # Bold text
            bold_start = remaining.find('**')
            if bold_start != -1:
                bold_end = remaining.find('**', bold_start + 2)
                if bold_end != -1:
                    if bold_start > 0:
                        text_content.append({"type": "text", "text": remaining[:bold_start]})
                    text_content.append({
                        "type": "text",
                        "text": remaining[bold_start + 2:bold_end],
                        "marks": [{"type": "strong"}]
                    })
                    remaining = remaining[bold_end + 2:]
                    continue
            
            # No more formatting - add rest as plain text
            if remaining:
                text_content.append({"type": "text", "text": remaining})
            break
        
        if text_content:
            content.append({
                "type": "paragraph",
                "content": text_content
            })
        i += 1
    
    return {
        "type": "doc",
        "version": 1,
        "content": content if content else [{"type": "paragraph", "content": [{"type": "text", "text": markdown_text}]}]
    }


async def create_subtask(
    jira_service,
    parent_key: str,
    summary: str,
    description: str = "",
    priority: str = "Medium"
) -> str:
    """Create a subtask under an existing JIRA issue.
    
    Args:
        jira_service: JiraService instance
        parent_key: Parent ticket key (e.g., PROJ-123)
        summary: Subtask summary/title
        description: Subtask description
        priority: Priority level
        
    Returns:
        Success/failure message
    """
    settings = jira_service.settings
    parent_key = parent_key.strip().upper()
    
    log_info(f"📋 Creating subtask under {parent_key}: {summary}", "jira_agent")
    
    auth = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()
    
    jira_base_url = f"https://{settings.jira_instance_url}/rest/api/3"
    
    # Build description in ADF format
    adf_description = markdown_to_adf(description)
    
    issue_data = {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "parent": {"key": parent_key},
            "summary": summary,
            "description": adf_description,
            "issuetype": {"name": "Sub-task"},
        }
    }
    
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
            return f"✅ Created subtask **{ticket_key}** under {parent_key}: {summary}"
        else:
            error_detail = response.text
            log_error(f"JIRA subtask create error: {error_detail}", "jira_agent")
            return f"❌ Failed to create subtask: {response.status_code} - {error_detail}"


async def link_issues(
    jira_service,
    source_key: str,
    target_key: str,
    link_type: str = "Relates"
) -> str:
    """Link two JIRA issues together.
    
    Args:
        jira_service: JiraService instance
        source_key: Source ticket key (e.g., PROJ-123)
        target_key: Target ticket key to link to
        link_type: Type of link (Relates, Blocks, is blocked by, Duplicates, etc.)
        
    Returns:
        Success/failure message
    """
    settings = jira_service.settings
    source_key = source_key.strip().upper()
    target_key = target_key.strip().upper()
    
    log_info(f"🔗 Linking {source_key} -> {target_key} ({link_type})", "jira_agent")
    
    auth = base64.b64encode(
        f"{settings.jira_email}:{settings.jira_api_token}".encode()
    ).decode()
    
    jira_base_url = f"https://{settings.jira_instance_url}/rest/api/3"
    
    # Map common link type names to JIRA link type names
    link_type_map = {
        "relates": "Relates",
        "relates to": "Relates",
        "blocks": "Blocks",
        "is blocked by": "Blocks",
        "blocked by": "Blocks",
        "duplicates": "Duplicate",
        "duplicate": "Duplicate",
        "is duplicated by": "Duplicate",
        "clones": "Cloners",
        "is cloned by": "Cloners",
        "causes": "Problem/Incident",
        "is caused by": "Problem/Incident",
    }
    
    # Normalize link type
    normalized_link_type = link_type_map.get(link_type.lower(), link_type)
    
    link_data = {
        "type": {"name": normalized_link_type},
        "inwardIssue": {"key": source_key},
        "outwardIssue": {"key": target_key}
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{jira_base_url}/issueLink",
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json=link_data
        )
        
        if response.status_code == 201:
            return f"✅ Linked **{source_key}** to **{target_key}** ({normalized_link_type})"
        else:
            error_detail = response.text
            log_error(f"JIRA link error: {error_detail}", "jira_agent")
            
            # Try to get available link types for better error message
            if "linkType" in error_detail.lower():
                try:
                    link_types_response = await client.get(
                        f"{jira_base_url}/issueLinkType",
                        headers={
                            "Authorization": f"Basic {auth}",
                            "Accept": "application/json"
                        }
                    )
                    if link_types_response.status_code == 200:
                        types = link_types_response.json().get("issueLinkTypes", [])
                        type_names = [t.get("name") for t in types]
                        return f"❌ Invalid link type '{link_type}'. Available types: {', '.join(type_names)}"
                except Exception:
                    pass
            
            return f"❌ Failed to link issues: {response.status_code} - {error_detail}"
