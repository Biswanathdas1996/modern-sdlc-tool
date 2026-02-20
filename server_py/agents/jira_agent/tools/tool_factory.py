"""Factory for creating LangChain tools for JIRA operations."""
from typing import List
from langchain_core.tools import Tool

from .ticket_tools import (
    TicketToolsContext,
    search_tickets_tool,
    get_details_tool,
    create_ticket_tool,
    update_ticket_tool,
    bulk_update_tool,
    get_last_results_tool,
    create_subtask_tool,
    link_issues_tool,
    make_async_sync
)
from .knowledge_base import (
    search_knowledge_base_tool,
    get_knowledge_stats_tool,
    query_mongodb_tool
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
        Tool(
            name="search_knowledge_base",
            description="""Search the knowledge base for relevant documentation and information.
            Use this tool when the user wants to:
            - Find information from uploaded documents
            - Search for documentation, guidelines, or requirements
            - Look up context from the knowledge base
            
            Input should be a search query string.
            Examples: "authentication requirements", "API documentation", "security guidelines", "Compliance Audit Workflow"
            
            CRITICAL: After receiving search results, you MUST:
            1. Read and understand the content provided
            2. Synthesize the information (don't copy-paste raw chunks)
            3. Create well-structured, formatted output appropriate for the task
            4. For JIRA tickets: Use clear sections with headers, bullet points, and proper markdown
            5. Focus on the specific user request - extract only relevant portions
            6. Format professionally with proper spacing and structure
            
            Note: Searches within the current project's knowledge base collection.
            """,
            func=make_async_sync(lambda q: search_knowledge_base_tool(q, context.project_id or "global", 10)),
            coroutine=lambda q: search_knowledge_base_tool(q, context.project_id or "global", 10)
        ),
        Tool(
            name="get_knowledge_stats",
            description="""Get statistics about the knowledge base.
            Use this tool when the user asks about:
            - How many documents are in the knowledge base
            - Knowledge base size or statistics
            - What's available in the documentation
            
            No input required (or use "default" for default project).
            """,
            func=make_async_sync(lambda p: get_knowledge_stats_tool(context.project_id or "global")),
            coroutine=lambda p: get_knowledge_stats_tool(context.project_id or "global")
        ),
        Tool(
            name="query_mongodb",
            description="""Query MongoDB directly with custom filters.
            Use this tool for advanced database queries when you need to:
            - Retrieve specific data from MongoDB collections
            - Execute custom queries with filters
            - Access raw data from the database
            
            Input should be a JSON string with: collection (required), query (required as JSON string), limit (optional, default: 10)
            
            IMPORTANT: Knowledge base data is stored in project-specific collections.
            For the current project, chunks are in the collection named with the project ID suffix.
            Field names in chunk collections:
            - "content" (not "text") - the actual text content
            - "documentId" - the document identifier
            - "metadata.filename" - the source file name
            
            Prefer using the search_knowledge_base tool instead of raw MongoDB queries for knowledge base searches.
            """,
            func=make_async_sync(_create_query_mongodb_wrapper()),
            coroutine=_create_query_mongodb_wrapper()
        ),
        Tool(
            name="create_subtask",
            description="""Create a subtask under an existing JIRA ticket.
            Use this tool when the user wants to:
            - Create a subtask for an existing story/bug/task
            - Add a child task to a parent ticket
            - Break down a ticket into smaller tasks
            
            Input should be a JSON string with: 
            - parent_key (required): The parent ticket key (e.g., "PROJ-123")
            - summary (required): Subtask summary/title
            - description (optional): Subtask description
            - priority (optional): Low/Medium/High/Critical, default: Medium
            
            Example: {"parent_key": "PROJ-123", "summary": "Implement unit tests", "description": "Add tests for login feature"}
            """,
            func=make_async_sync(lambda j: create_subtask_tool(jira_service, j)),
            coroutine=lambda j: create_subtask_tool(jira_service, j)
        ),
        Tool(
            name="link_issues",
            description="""Link two JIRA issues together.
            Use this tool when the user wants to:
            - Link a story to another ticket
            - Create relationships between issues (relates to, blocks, duplicates, etc.)
            - Connect related tickets
            
            Input should be a JSON string with:
            - source_key (required): The source ticket key (e.g., "PROJ-123")
            - target_key (required): The target ticket key to link to
            - link_type (optional): Type of link - "Relates", "Blocks", "Duplicates", etc. Default: "Relates"
            
            Available link types: Relates, Blocks, is blocked by, Duplicates, Clones
            
            Example: {"source_key": "PROJ-123", "target_key": "PROJ-456", "link_type": "Blocks"}
            """,
            func=make_async_sync(lambda j: link_issues_tool(jira_service, j)),
            coroutine=lambda j: link_issues_tool(jira_service, j)
        ),
    ]


def _create_query_mongodb_wrapper():
    """Create a wrapper function for query_mongodb_tool that handles JSON parsing."""
    import json
    
    async def wrapper(input_json: str):
        try:
            params = json.loads(input_json)
            collection = params.get('collection')
            query = params.get('query', '{}')
            limit = params.get('limit', 10)
            
            if not collection:
                return "Error: 'collection' parameter is required"
            
            return await query_mongodb_tool(collection, query, limit)
        except json.JSONDecodeError as e:
            return f"Error parsing JSON input: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    return wrapper
