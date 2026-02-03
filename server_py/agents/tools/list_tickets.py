"""Tool for listing all JIRA tickets."""
import asyncio
from langchain_core.tools import Tool

from core.logging import log_debug, log_error


def create_list_tickets_tool(jira_agent_instance) -> Tool:
    """Create the list_all_tickets tool.
    
    Args:
        jira_agent_instance: Instance of JiraAgent to access jira_service
        
    Returns:
        Tool: LangChain tool for listing all tickets
    """
    
    def list_all_tickets_sync(dummy: str) -> str:
        """List all available JIRA tickets in the project. Use this to get an overview."""
        try:
            log_debug(f"Tool called: list_all_tickets", "jira_agent")
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                stories = loop.run_until_complete(jira_agent_instance.jira_service.get_jira_stories())
            else:
                stories = loop.run_until_complete(jira_agent_instance.jira_service.get_jira_stories())
            
            if not stories:
                return "No JIRA tickets found in the project."
            
            # Return summary of all tickets
            summary = [f"{s['key']}: {s['summary']} (Status: {s['status']})" 
                      for s in stories[:10]]
            return "\n".join(summary) + f"\n\nTotal tickets: {len(stories)}"
        except Exception as e:
            log_error(f"Error in list_all_tickets_sync", "jira_agent", e)
            return f"Error listing tickets: {str(e)}"
    
    return Tool(
        name="list_all_tickets",
        func=list_all_tickets_sync,
        description="List all available JIRA tickets in the project. Use this when the user wants to see all tickets or get an overview. Input can be any string (it will be ignored)."
    )
