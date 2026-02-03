"""Tool for getting JIRA ticket details."""
import asyncio
from langchain_core.tools import Tool

from core.logging import log_debug, log_error
from .ticket_details_logic import get_ticket_details


def create_ticket_details_tool(jira_agent_instance) -> Tool:
    """Create the get_ticket_details tool.
    
    Args:
        jira_agent_instance: Instance of JiraAgent to access jira_service
        
    Returns:
        Tool: LangChain tool for getting ticket details
    """
    
    def get_ticket_details_sync(ticket_key: str) -> str:
        """Get detailed information about a specific JIRA ticket. Input should be a JIRA ticket key like 'KAN-123'."""
        try:
            log_debug(f"Tool called: get_ticket_details with key='{ticket_key}'", "jira_agent")
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                result = loop.run_until_complete(get_ticket_details(jira_agent_instance.jira_service, ticket_key))
            else:
                result = loop.run_until_complete(get_ticket_details(jira_agent_instance.jira_service, ticket_key))
            
            if not result:
                return f"Could not find details for ticket {ticket_key}"
            
            return result
        except Exception as e:
            log_error(f"Error in get_ticket_details_sync", "jira_agent", e)
            return f"Error getting ticket details: {str(e)}"
    
    return Tool(
        name="get_ticket_details",
        func=get_ticket_details_sync,
        description="Get detailed information about a specific JIRA ticket including full description, comments, and context. Input should be a JIRA ticket key (e.g., 'KAN-123')."
    )
