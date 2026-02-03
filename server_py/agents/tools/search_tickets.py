"""Tool for searching JIRA tickets."""
import asyncio
from langchain_core.tools import Tool

from core.logging import log_debug, log_error
from .search import search_jira_tickets
from .helpers import format_tickets_for_agent


def create_search_tickets_tool(jira_agent_instance) -> Tool:
    """Create the search_jira_tickets tool.
    
    Args:
        jira_agent_instance: Instance of JiraAgent to access jira_service
        
    Returns:
        Tool: LangChain tool for searching JIRA tickets
    """
    
    def search_jira_tickets_sync(query: str) -> str:
        """Search for JIRA tickets based on a query. Input should be a search query string."""
        try:
            log_debug(f"Tool called: search_jira_tickets with query='{query}'", "jira_agent")
            # Run async function in sync context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                result = loop.run_until_complete(search_jira_tickets(jira_agent_instance.jira_service, query))
            else:
                result = loop.run_until_complete(search_jira_tickets(jira_agent_instance.jira_service, query))
            
            if not result:
                return "No JIRA tickets found matching the query."
            
            return format_tickets_for_agent(result[:5])  # Return top 5
        except Exception as e:
            log_error(f"Error in search_jira_tickets_sync", "jira_agent", e)
            return f"Error searching tickets: {str(e)}"
    
    return Tool(
        name="search_jira_tickets",
        func=search_jira_tickets_sync,
        description="Search for JIRA tickets based on keywords or description. Input should be a search query string describing what you're looking for. Returns a list of relevant tickets with their keys, summaries, status, and descriptions."
    )
