"""Tool wrapper functions for JIRA ticket operations."""
import json
import asyncio
from typing import List, Dict, Any

from core.logging import log_info, log_error
from .search import search_jira_tickets, search_with_jql
from .jira_operations import (
    create_jira_issue, 
    update_jira_issue, 
    get_ticket_details,
    create_subtask,
    link_issues,
    markdown_to_adf
)


class TicketToolsContext:
    """Context for ticket tools to share state."""
    
    def __init__(self):
        self.last_search_results: List[Dict[str, Any]] = []


def make_async_sync(async_func):
    """Convert async function to sync for LangChain tools."""
    def sync_wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(async_func(*args, **kwargs))
    return sync_wrapper


async def search_tickets_tool(jira_service, context: TicketToolsContext, query: str, ai_service=None) -> str:
    """Search for JIRA tickets using LLM-generated JQL.
    
    Args:
        jira_service: JiraService instance
        context: Shared context for storing results
        query: Natural language search query
        ai_service: Optional AI service for JQL generation
        
    Returns:
        Formatted search results
    """
    try:
        log_info(f"🔍 Searching tickets: {query}", "jira_agent")
        
        # Use JQL-based search if AI service is available
        if ai_service:
            project_key = getattr(jira_service.settings, 'jira_project_key', None)
            tickets = await search_with_jql(jira_service, ai_service, query, project_key)
        else:
            tickets = await search_jira_tickets(jira_service, query)
        
        # Store for chained operations
        context.last_search_results = tickets
        
        if not tickets:
            return f"No tickets found matching: '{query}'"
        
        result = f"Found {len(tickets)} ticket(s):\n\n"
        for ticket in tickets:
            result += f"- **{ticket.get('key')}**: {ticket.get('summary')}\n"
            result += f"  Type: {ticket.get('issueType', 'Unknown')} | Status: {ticket.get('status')} | Priority: {ticket.get('priority')}\n"
            if ticket.get('assignee'):
                result += f"  Assignee: {ticket.get('assignee')}\n"
            if ticket.get('labels'):
                result += f"  Labels: {', '.join(ticket.get('labels', []))}\n"
            if ticket.get('components'):
                result += f"  Components: {', '.join(ticket.get('components', []))}\n"
            result += "\n"
        
        return result
        
    except Exception as e:
        log_error(f"Search error: {e}", "jira_agent", e)
        return f"Error searching tickets: {str(e)}"


async def get_details_tool(jira_service, ticket_key: str) -> str:
    """Get details for a specific ticket.
    
    Args:
        jira_service: JiraService instance
        ticket_key: JIRA ticket key
        
    Returns:
        Formatted ticket details
    """
    try:
        return await get_ticket_details(jira_service, ticket_key)
    except Exception as e:
        log_error(f"Get details error: {e}", "jira_agent", e)
        return f"Error getting ticket details: {str(e)}"


async def create_ticket_tool(jira_service, input_json: str) -> str:
    """Create a new JIRA ticket.
    
    Args:
        jira_service: JiraService instance
        input_json: JSON string with ticket details
        
    Returns:
        Success/failure message
    """
    try:
        # Parse input
        if isinstance(input_json, str):
            data = json.loads(input_json)
        else:
            data = input_json
        
        summary = data.get('summary')
        description = data.get('description', '')
        issue_type = data.get('issue_type', 'Story')
        priority = data.get('priority', 'Medium')
        labels = data.get('labels', [])
        
        if not summary:
            return "Error: 'summary' is required to create a ticket"
        
        log_info(f"📝 Creating ticket: {summary}", "jira_agent")
        
        return await create_jira_issue(
            jira_service=jira_service,
            summary=summary,
            description=description,
            issue_type=issue_type,
            priority=priority,
            labels=labels
        )
        
    except json.JSONDecodeError as e:
        return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
    except Exception as e:
        log_error(f"Create ticket error: {e}", "jira_agent", e)
        return f"Error creating ticket: {str(e)}"


async def update_ticket_tool(jira_service, input_json: str) -> str:
    """Update an existing JIRA ticket.
    
    Args:
        jira_service: JiraService instance
        input_json: JSON string with update details
        
    Returns:
        Success/failure message
    """
    try:
        # Parse input
        if isinstance(input_json, str):
            data = json.loads(input_json)
        else:
            data = input_json
        
        ticket_key = data.get('ticket_key')
        if not ticket_key:
            return "Error: 'ticket_key' is required to update a ticket"
        
        ticket_key = ticket_key.strip().upper()
        log_info(f"✏️ Updating ticket: {ticket_key}", "jira_agent")
        
        # Build update fields
        update_fields = {}
        if data.get('summary'):
            update_fields['summary'] = data['summary']
        if data.get('description'):
            update_fields['description'] = data['description']
        if data.get('priority'):
            update_fields['priority'] = data['priority']
        if data.get('labels'):
            update_fields['labels'] = data['labels']
        
        return await update_jira_issue(
            jira_service=jira_service,
            ticket_key=ticket_key,
            fields=update_fields,
            status=data.get('status'),
            comment=data.get('comment')
        )
        
    except json.JSONDecodeError as e:
        return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
    except Exception as e:
        log_error(f"Update ticket error: {e}", "jira_agent", e)
        return f"Error updating ticket: {str(e)}"


async def bulk_update_tool(jira_service, context: TicketToolsContext, input_json: str) -> str:
    """Update multiple tickets from last search results.
    
    Args:
        jira_service: JiraService instance
        context: Shared context with last search results
        input_json: JSON string with update fields
        
    Returns:
        Summary of bulk update results
    """
    try:
        if not context.last_search_results:
            return "No previous search results. Please search for tickets first."
        
        # Parse input
        if isinstance(input_json, str):
            data = json.loads(input_json)
        else:
            data = input_json
        
        log_info(f"📦 Bulk updating {len(context.last_search_results)} tickets", "jira_agent")
        
        results = []
        for ticket in context.last_search_results:
            ticket_key = ticket.get('key')
            try:
                update_data = {'ticket_key': ticket_key, **data}
                result = await update_ticket_tool(jira_service, json.dumps(update_data))
                results.append(f"✅ {ticket_key}: Updated successfully")
            except Exception as e:
                results.append(f"❌ {ticket_key}: {str(e)}")
        
        return f"Bulk update completed:\n" + "\n".join(results)
        
    except json.JSONDecodeError as e:
        return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
    except Exception as e:
        log_error(f"Bulk update error: {e}", "jira_agent", e)
        return f"Error in bulk update: {str(e)}"


def get_last_results_tool(context: TicketToolsContext, _: str = "") -> str:
    """Get the last search results.
    
    Args:
        context: Shared context with last search results
        _: Unused parameter (for tool compatibility)
        
    Returns:
        Formatted last search results
    """
    if not context.last_search_results:
        return "No previous search results available."
    
    result = f"Last search found {len(context.last_search_results)} ticket(s):\n\n"
    for ticket in context.last_search_results:
        result += f"- **{ticket.get('key')}**: {ticket.get('summary')} ({ticket.get('status')})\n"
    
    return result


async def create_subtask_tool(jira_service, input_json: str) -> str:
    """Create a subtask under an existing JIRA ticket.
    
    Args:
        jira_service: JiraService instance
        input_json: JSON string with subtask details
        
    Returns:
        Success/failure message
    """
    try:
        if isinstance(input_json, str):
            data = json.loads(input_json)
        else:
            data = input_json
        
        parent_key = data.get('parent_key')
        summary = data.get('summary')
        description = data.get('description', '')
        priority = data.get('priority', 'Medium')
        
        if not parent_key:
            return "Error: 'parent_key' is required to create a subtask"
        if not summary:
            return "Error: 'summary' is required to create a subtask"
        
        log_info(f"📝 Creating subtask under {parent_key}: {summary}", "jira_agent")
        
        return await create_subtask(
            jira_service=jira_service,
            parent_key=parent_key,
            summary=summary,
            description=description,
            priority=priority
        )
        
    except json.JSONDecodeError as e:
        return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
    except Exception as e:
        log_error(f"Create subtask error: {e}", "jira_agent", e)
        return f"Error creating subtask: {str(e)}"


async def link_issues_tool(jira_service, input_json: str) -> str:
    """Link two JIRA issues together.
    
    Args:
        jira_service: JiraService instance
        input_json: JSON string with link details
        
    Returns:
        Success/failure message
    """
    try:
        if isinstance(input_json, str):
            data = json.loads(input_json)
        else:
            data = input_json
        
        source_key = data.get('source_key')
        target_key = data.get('target_key')
        link_type = data.get('link_type', 'Relates')
        
        if not source_key:
            return "Error: 'source_key' is required to link issues"
        if not target_key:
            return "Error: 'target_key' is required to link issues"
        
        log_info(f"🔗 Linking {source_key} to {target_key}", "jira_agent")
        
        return await link_issues(
            jira_service=jira_service,
            source_key=source_key,
            target_key=target_key,
            link_type=link_type
        )
        
    except json.JSONDecodeError as e:
        return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
    except Exception as e:
        log_error(f"Link issues error: {e}", "jira_agent", e)
        return f"Error linking issues: {str(e)}"
