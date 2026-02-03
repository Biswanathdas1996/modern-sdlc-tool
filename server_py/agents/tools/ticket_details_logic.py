"""Ticket details retrieval logic."""
from typing import Optional

from core.logging import log_info, log_error


async def get_ticket_details(jira_service, ticket_key: str) -> Optional[str]:
    """Get detailed information about a specific JIRA ticket.
    
    Args:
        jira_service: JiraService instance
        ticket_key: JIRA ticket key (e.g., 'KAN-123')
        
    Returns:
        Detailed ticket context or None if not found
    """
    try:
        log_info(f"Getting details for ticket: {ticket_key}", "jira_agent")
        context = await jira_service.get_parent_story_context(ticket_key)
        return context
    except Exception as e:
        log_error(f"Error getting ticket details", "jira_agent", e)
        return None
