"""Factory for creating LangChain tools for JIRA operations."""
from typing import List
from langchain.tools import Tool

from .ticket_tools import (
    TicketToolsContext,
    search_tickets_tool,
    get_details_tool,
    create_ticket_tool,
    update_ticket_tool,
    bulk_update_tool,
    get_last_results_tool,
    make_async_sync
)


def create_jira_tools(jira_service, context: TicketToolsContext) -> List[Tool]:
    """Create LangChain tools for JIRA operations.
    
    Args:
        jira_service: JiraService instance for API calls
        context: Shared context for storing state between tool calls
        
    Returns:
        List of configured LangChain Tool instances
    """
    
    return [
        Tool(
            name="search_jira_tickets",
            description="""Search for JIRA tickets based on query criteria.
            Use this tool when the user wants to:
            - Find tickets by keywords, status, priority, or labels
            - List tickets matching certain conditions
            - Search for related issues
            
            Input should be a search query string describing what to find.
            Examples: "in progress tickets", "bugs related to login", "high priority stories"
            """,
            func=make_async_sync(lambda q: search_tickets_tool(jira_service, context, q)),
            coroutine=lambda q: search_tickets_tool(jira_service, context, q)
        ),
        Tool(
            name="get_ticket_details",
            description="""Get detailed information about a specific JIRA ticket.
            Use this tool when the user asks about a specific ticket by its key.
            
            Input should be the ticket key (e.g., "PROJ-123").
            """,
            func=make_async_sync(lambda k: get_details_tool(jira_service, k)),
            coroutine=lambda k: get_details_tool(jira_service, k)
        ),
        Tool(
            name="create_jira_ticket",
            description="""Create a new JIRA ticket.
            Use this tool when the user wants to:
            - Create a new story, bug, or task
            - Add a new issue to JIRA
            
            Input should be a JSON string with: summary (required), description (required),
            issue_type (optional: Story/Bug/Task, default: Story), 
            priority (optional: Low/Medium/High/Critical, default: Medium),
            labels (optional: list of strings)
            
            Example: {"summary": "Implement login feature", "description": "Add OAuth2 login", "issue_type": "Story", "priority": "High"}
            """,
            func=make_async_sync(lambda j: create_ticket_tool(jira_service, j)),
            coroutine=lambda j: create_ticket_tool(jira_service, j)
        ),
        Tool(
            name="update_jira_ticket",
            description="""Update an existing JIRA ticket.
            Use this tool when the user wants to:
            - Change ticket status (To Do, In Progress, Done, etc.)
            - Update description or summary
            - Add comments
            - Change priority or labels
            
            Input should be a JSON string with: ticket_key (required),
            and any of: summary, description, status, priority, labels, comment
            
            Example: {"ticket_key": "PROJ-123", "status": "In Progress", "comment": "Starting work on this"}
            """,
            func=make_async_sync(lambda j: update_ticket_tool(jira_service, j)),
            coroutine=lambda j: update_ticket_tool(jira_service, j)
        ),
        Tool(
            name="bulk_update_tickets",
            description="""Update multiple JIRA tickets from the last search results.
            Use this tool for chained operations like "find all in-progress tickets and mark them as done".
            
            Input should be a JSON string with the update fields to apply to all tickets.
            The tickets to update come from the most recent search.
            
            Fields: status, priority, labels, comment
            Example: {"status": "Done", "comment": "Closing as part of sprint cleanup"}
            """,
            func=make_async_sync(lambda j: bulk_update_tool(jira_service, context, j)),
            coroutine=lambda j: bulk_update_tool(jira_service, context, j)
        ),
        Tool(
            name="get_last_search_results",
            description="""Get the tickets from the most recent search.
            Use this to reference previously found tickets for updates or follow-up questions.
            No input required.
            """,
            func=lambda _: get_last_results_tool(context, _),
            coroutine=lambda _: get_last_results_tool(context, _)
        ),
    ]
