"""
Robust LangChain-based JIRA Agent with intelligent query analysis.
Supports: Search, Create, Update tickets, and chained operations (search -> update).
"""
import json
import re
from typing import Dict, Any, List, Optional, Union
from enum import Enum

from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool, StructuredTool
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from services.jira_service import JiraService
from services.ai_service import AIService
from services.langchain_llm import PwCGenAILLM
from core.logging import log_info, log_error, log_debug
from .tools import search_jira_tickets, format_tickets_for_agent


class ActionType(Enum):
    """Types of actions the agent can perform."""
    SEARCH = "search"
    CREATE = "create"
    UPDATE = "update"
    SEARCH_AND_UPDATE = "search_and_update"
    GET_DETAILS = "get_details"
    UNKNOWN = "unknown"


class TicketCreateInput(BaseModel):
    """Input schema for creating a ticket."""
    summary: str = Field(description="The ticket summary/title")
    description: str = Field(description="Detailed description of the ticket")
    issue_type: str = Field(default="Story", description="Issue type: Story, Bug, Task, Sub-task")
    priority: str = Field(default="Medium", description="Priority: Low, Medium, High, Critical")
    labels: List[str] = Field(default_factory=list, description="Labels to add to the ticket")


class TicketUpdateInput(BaseModel):
    """Input schema for updating a ticket."""
    ticket_key: str = Field(description="The JIRA ticket key (e.g., PROJ-123)")
    summary: Optional[str] = Field(default=None, description="New summary/title")
    description: Optional[str] = Field(default=None, description="New description")
    status: Optional[str] = Field(default=None, description="New status: To Do, In Progress, Done")
    priority: Optional[str] = Field(default=None, description="New priority")
    labels: Optional[List[str]] = Field(default=None, description="Labels to set")
    comment: Optional[str] = Field(default=None, description="Comment to add to the ticket")


class JiraAgent:
    """
    Intelligent JIRA Agent using LangChain for robust query understanding.
    
    Capabilities:
    - Search tickets by keywords, status, priority, labels
    - Create new tickets with full details
    - Update existing tickets (status, description, comments)
    - Chained operations: search -> update multiple tickets
    """
    
    def __init__(self):
        """Initialize the JIRA agent with LangChain components."""
        self.jira_service = JiraService()
        self.ai_service = AIService()
        self.llm = PwCGenAILLM(temperature=0.2, max_tokens=4096)
        
        # Context storage for chained operations
        self._last_search_results: List[Dict[str, Any]] = []
        self._conversation_context: List[Dict[str, str]] = []
        
        # Initialize tools
        self.tools = self._create_tools()
        
        # Create the agent
        self.agent = self._create_agent()
        
    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools for JIRA operations."""
        
        # Tool 1: Search Tickets
        search_tool = Tool(
            name="search_jira_tickets",
            description="""Search for JIRA tickets based on query criteria.
            Use this tool when the user wants to:
            - Find tickets by keywords, status, priority, or labels
            - List tickets matching certain conditions
            - Search for related issues
            
            Input should be a search query string describing what to find.
            Examples: "in progress tickets", "bugs related to login", "high priority stories"
            """,
            func=self._search_tickets_sync,
            coroutine=self._search_tickets
        )
        
        # Tool 2: Get Ticket Details
        details_tool = Tool(
            name="get_ticket_details",
            description="""Get detailed information about a specific JIRA ticket.
            Use this tool when the user asks about a specific ticket by its key.
            
            Input should be the ticket key (e.g., "PROJ-123").
            """,
            func=self._get_ticket_details_sync,
            coroutine=self._get_ticket_details
        )
        
        # Tool 3: Create Ticket
        create_tool = Tool(
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
            func=self._create_ticket_sync,
            coroutine=self._create_ticket
        )
        
        # Tool 4: Update Ticket
        update_tool = Tool(
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
            func=self._update_ticket_sync,
            coroutine=self._update_ticket
        )
        
        # Tool 5: Bulk Update (for search -> update operations)
        bulk_update_tool = Tool(
            name="bulk_update_tickets",
            description="""Update multiple JIRA tickets from the last search results.
            Use this tool for chained operations like "find all in-progress tickets and mark them as done".
            
            Input should be a JSON string with the update fields to apply to all tickets.
            The tickets to update come from the most recent search.
            
            Fields: status, priority, labels, comment
            Example: {"status": "Done", "comment": "Closing as part of sprint cleanup"}
            """,
            func=self._bulk_update_sync,
            coroutine=self._bulk_update_tickets
        )
        
        # Tool 6: Get Last Search Results
        last_results_tool = Tool(
            name="get_last_search_results",
            description="""Get the tickets from the most recent search.
            Use this to reference previously found tickets for updates or follow-up questions.
            No input required.
            """,
            func=self._get_last_search_results,
            coroutine=self._get_last_search_results_async
        )
        
        return [search_tool, details_tool, create_tool, update_tool, bulk_update_tool, last_results_tool]
    
    def _create_agent(self) -> AgentExecutor:
        """Create the LangChain ReAct agent with robust parsing."""
        
        prompt_template = """You are an intelligent JIRA assistant that helps users manage their JIRA tickets.
You can search, create, update, and perform bulk operations on tickets.

IMPORTANT RULES:
1. For SEARCH queries: Use search_jira_tickets tool with descriptive search terms
2. For CREATE requests: Extract summary, description, type, and priority from the user's message
3. For UPDATE requests: Identify the ticket key and what fields to update
4. For CHAINED operations (e.g., "find X and update Y"): First search, then use bulk_update_tickets
5. Always provide clear, actionable responses with ticket keys and details
6. If a user refers to "these tickets" or "them", use get_last_search_results

CRITICAL FORMAT RULES:
- You must EITHER use an Action OR give a Final Answer, NEVER BOTH in the same response
- After getting an Observation, decide if you need another Action or can give Final Answer
- When you have enough information, respond ONLY with "Final Answer:" followed by your response

Available tools:
{tools}

Tool names: {tool_names}

FORMAT (follow exactly):

Question: the user's question or request
Thought: I need to [analyze what action to take]
Action: [tool name]
Action Input: [input for the tool]

After receiving an Observation, continue with:
Thought: [analyze the observation and decide next step]
Action: [next tool if needed]
Action Input: [input]

OR if you have enough information:
Thought: I now have the information to answer the user's question
Final Answer: [your helpful response to the user]

REMEMBER: Never put Action and Final Answer in the same response block!

Begin!

Question: {input}
{agent_scratchpad}"""

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["input", "tools", "tool_names", "agent_scratchpad"]
        )
        
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=self._handle_parsing_error,
            max_iterations=5,
            return_intermediate_steps=True
        )
    
    def _handle_parsing_error(self, error: Exception) -> str:
        """Handle parsing errors gracefully."""
        error_msg = str(error)
        log_error(f"Agent parsing error: {error_msg}", "jira_agent")
        
        # Try to extract Final Answer from the error message
        if "Final Answer:" in error_msg:
            match = re.search(r"Final Answer:\s*(.+?)(?:Action:|Observation:|$)", error_msg, re.DOTALL | re.IGNORECASE)
            if match:
                answer = match.group(1).strip()
                log_info(f"Extracted answer from parsing error: {answer[:100]}...", "jira_agent")
                return answer
        
        # Try to extract any meaningful text
        if "Parsing LLM output produced both" in error_msg:
            # This is the specific error we're seeing - extract the final answer
            lines = error_msg.split('\n')
            for i, line in enumerate(lines):
                if 'Final Answer:' in line and i + 1 < len(lines):
                    # Get the line after "Final Answer:"
                    answer_line = lines[i].split('Final Answer:')[-1].strip()
                    if answer_line:
                        return answer_line
                    # Or get the next line
                    if i + 1 < len(lines):
                        return lines[i + 1].strip()
        
        return "I encountered an issue processing the response. Let me try a simpler approach."
    
    # ==================== TOOL IMPLEMENTATIONS ====================
    
    async def _search_tickets(self, query: str) -> str:
        """Search for JIRA tickets."""
        try:
            log_info(f"🔍 Searching tickets: {query}", "jira_agent")
            tickets = await search_jira_tickets(self.jira_service, query)
            
            # Store for chained operations
            self._last_search_results = tickets
            
            if not tickets:
                return f"No tickets found matching: '{query}'"
            
            result = f"Found {len(tickets)} ticket(s):\n\n"
            for ticket in tickets:
                result += f"- **{ticket.get('key')}**: {ticket.get('summary')}\n"
                result += f"  Status: {ticket.get('status')} | Priority: {ticket.get('priority')}\n"
                if ticket.get('labels'):
                    result += f"  Labels: {', '.join(ticket.get('labels', []))}\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            log_error(f"Search error: {e}", "jira_agent", e)
            return f"Error searching tickets: {str(e)}"
    
    def _search_tickets_sync(self, query: str) -> str:
        """Synchronous wrapper for search."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._search_tickets(query))
    
    async def _get_ticket_details(self, ticket_key: str) -> str:
        """Get details for a specific ticket."""
        try:
            ticket_key = ticket_key.strip().upper()
            log_info(f"📋 Getting details for: {ticket_key}", "jira_agent")
            
            # Search for the specific ticket
            tickets = await self.jira_service.get_jira_stories()
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
            
        except Exception as e:
            log_error(f"Get details error: {e}", "jira_agent", e)
            return f"Error getting ticket details: {str(e)}"
    
    def _get_ticket_details_sync(self, ticket_key: str) -> str:
        """Synchronous wrapper for get details."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._get_ticket_details(ticket_key))
    
    async def _create_ticket(self, input_json: str) -> str:
        """Create a new JIRA ticket."""
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
            
            # Create the ticket using jira_service
            result = await self._create_jira_issue(
                summary=summary,
                description=description,
                issue_type=issue_type,
                priority=priority,
                labels=labels
            )
            
            return result
            
        except json.JSONDecodeError as e:
            return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
        except Exception as e:
            log_error(f"Create ticket error: {e}", "jira_agent", e)
            return f"Error creating ticket: {str(e)}"
    
    def _create_ticket_sync(self, input_json: str) -> str:
        """Synchronous wrapper for create ticket."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._create_ticket(input_json))
    
    async def _update_ticket(self, input_json: str) -> str:
        """Update an existing JIRA ticket."""
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
            
            # Perform update
            result = await self._update_jira_issue(
                ticket_key=ticket_key,
                fields=update_fields,
                status=data.get('status'),
                comment=data.get('comment')
            )
            
            return result
            
        except json.JSONDecodeError as e:
            return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
        except Exception as e:
            log_error(f"Update ticket error: {e}", "jira_agent", e)
            return f"Error updating ticket: {str(e)}"
    
    def _update_ticket_sync(self, input_json: str) -> str:
        """Synchronous wrapper for update ticket."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._update_ticket(input_json))
    
    async def _bulk_update_tickets(self, input_json: str) -> str:
        """Update multiple tickets from last search results."""
        try:
            if not self._last_search_results:
                return "No previous search results. Please search for tickets first."
            
            # Parse input
            if isinstance(input_json, str):
                data = json.loads(input_json)
            else:
                data = input_json
            
            log_info(f"📦 Bulk updating {len(self._last_search_results)} tickets", "jira_agent")
            
            results = []
            for ticket in self._last_search_results:
                ticket_key = ticket.get('key')
                try:
                    update_data = {'ticket_key': ticket_key, **data}
                    result = await self._update_ticket(json.dumps(update_data))
                    results.append(f"✅ {ticket_key}: Updated successfully")
                except Exception as e:
                    results.append(f"❌ {ticket_key}: {str(e)}")
            
            return f"Bulk update completed:\n" + "\n".join(results)
            
        except json.JSONDecodeError as e:
            return f"Error parsing input JSON: {str(e)}. Please provide valid JSON."
        except Exception as e:
            log_error(f"Bulk update error: {e}", "jira_agent", e)
            return f"Error in bulk update: {str(e)}"
    
    def _bulk_update_sync(self, input_json: str) -> str:
        """Synchronous wrapper for bulk update."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._bulk_update_tickets(input_json))
    
    def _get_last_search_results(self, _: str = "") -> str:
        """Get the last search results."""
        if not self._last_search_results:
            return "No previous search results available."
        
        result = f"Last search found {len(self._last_search_results)} ticket(s):\n\n"
        for ticket in self._last_search_results:
            result += f"- **{ticket.get('key')}**: {ticket.get('summary')} ({ticket.get('status')})\n"
        
        return result
    
    async def _get_last_search_results_async(self, _: str = "") -> str:
        """Async wrapper for get last search results."""
        return self._get_last_search_results(_)
    
    # ==================== JIRA API HELPERS ====================
    
    async def _create_jira_issue(
        self,
        summary: str,
        description: str,
        issue_type: str = "Story",
        priority: str = "Medium",
        labels: List[str] = None
    ) -> str:
        """Create a JIRA issue via API."""
        import httpx
        import base64
        
        settings = self.jira_service.settings
        
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
    
    async def _update_jira_issue(
        self,
        ticket_key: str,
        fields: Dict[str, Any] = None,
        status: str = None,
        comment: str = None
    ) -> str:
        """Update a JIRA issue via API."""
        import httpx
        import base64
        
        settings = self.jira_service.settings
        
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
    
    # ==================== INTENT ANALYSIS ====================
    
    async def _analyze_intent(self, user_prompt: str) -> Dict[str, Any]:
        """Analyze user intent to determine the action type."""
        prompt_lower = user_prompt.lower()
        
        # Detect action patterns
        create_patterns = ['create', 'add', 'new ticket', 'make a', 'open a ticket', 'raise a']
        update_patterns = ['update', 'change', 'modify', 'set status', 'mark as', 'move to', 'transition']
        search_patterns = ['find', 'search', 'show', 'list', 'get', 'what are', 'which tickets']
        chained_patterns = ['and update', 'and change', 'then update', 'then mark', 'and mark']
        
        is_search = any(p in prompt_lower for p in search_patterns)
        is_create = any(p in prompt_lower for p in create_patterns)
        is_update = any(p in prompt_lower for p in update_patterns)
        is_chained = any(p in prompt_lower for p in chained_patterns)
        
        # Detect ticket key in prompt
        ticket_key_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
        specific_ticket = ticket_key_match.group(1) if ticket_key_match else None
        
        if is_search and is_chained:
            return {"action": ActionType.SEARCH_AND_UPDATE, "ticket_key": specific_ticket}
        elif is_create:
            return {"action": ActionType.CREATE, "ticket_key": specific_ticket}
        elif is_update and specific_ticket:
            return {"action": ActionType.UPDATE, "ticket_key": specific_ticket}
        elif specific_ticket and not is_search:
            return {"action": ActionType.GET_DETAILS, "ticket_key": specific_ticket}
        elif is_search:
            return {"action": ActionType.SEARCH, "ticket_key": specific_ticket}
        else:
            return {"action": ActionType.UNKNOWN, "ticket_key": specific_ticket}
    
    # ==================== MAIN ENTRY POINTS ====================
    
    async def process_query(self, user_prompt: str) -> Dict[str, Any]:
        """
        Process a user query intelligently using LangChain agent.
        
        This is the main entry point that handles all types of JIRA operations.
        Falls back to direct processing if the agent encounters issues.
        
        Args:
            user_prompt: Natural language query from the user
            
        Returns:
            Dictionary with response, tickets found/created/updated, and metadata
        """
        try:
            log_info(f"🚀 Processing query: {user_prompt}", "jira_agent")
            print(f"\n{'='*80}")
            print(f"🤖 JIRA AGENT - Processing Query")
            print(f"{'='*80}")
            print(f"Query: {user_prompt}\n")
            
            # Analyze intent first for logging and fallback
            intent = await self._analyze_intent(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")
            print(f"🎯 Detected Intent: {intent['action'].value}")
            if intent.get('ticket_key'):
                print(f"🎫 Ticket Key Found: {intent['ticket_key']}")
            
            # Try LangChain agent first
            try:
                print(f"\n🔧 Running LangChain Agent...")
                result = await self._run_agent(user_prompt)
                agent_output = result.get("output", "")
                
                # Check if agent produced a meaningful response
                if agent_output and len(agent_output) > 20:
                    print(f"\n{'='*80}")
                    print(f"✅ JIRA AGENT COMPLETED")
                    print(f"{'='*80}\n")
                    
                    return {
                        "success": True,
                        "prompt": user_prompt,
                        "intent": intent['action'].value,
                        "response": agent_output,
                        "tickets": self._last_search_results,
                        "intermediate_steps": result.get("intermediate_steps", [])
                    }
                else:
                    raise Exception("Agent produced empty or minimal response")
                    
            except Exception as agent_error:
                log_error(f"Agent error, falling back to direct processing: {agent_error}", "jira_agent")
                print(f"⚠️ Agent encountered issue, using direct processing...")
                
                # Fallback to direct processing based on intent
                return await self._direct_process(user_prompt, intent)
            
        except Exception as e:
            log_error(f"Error processing query", "jira_agent", e)
            print(f"\n❌ ERROR: {str(e)}\n")
            return {
                "success": False,
                "prompt": user_prompt,
                "error": str(e),
                "response": f"I encountered an error: {str(e)}. Please try rephrasing your request.",
                "tickets": []
            }
    
    async def _direct_process(self, user_prompt: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Direct processing without LangChain agent as a fallback.
        Uses intent analysis to route to appropriate action.
        """
        action = intent.get('action', ActionType.UNKNOWN)
        ticket_key = intent.get('ticket_key')
        
        try:
            if action == ActionType.SEARCH or action == ActionType.UNKNOWN:
                # Default to search
                result = await self._search_tickets(user_prompt)
                
                # Generate AI analysis of results
                if self._last_search_results:
                    tickets_summary = format_tickets_for_agent(self._last_search_results)
                    analysis_prompt = f"""You are a JIRA assistant. A user asked: "{user_prompt}"

Here are the JIRA tickets found:

{tickets_summary}

Provide a concise summary including:
1. Number of tickets found
2. Key ticket IDs and summaries
3. Status information
4. Any relevant patterns"""
                    
                    ai_response = await self.ai_service.call_genai(
                        prompt=analysis_prompt,
                        temperature=0.3,
                        max_tokens=2000
                    )
                    response = ai_response
                else:
                    response = result
                
                return {
                    "success": True,
                    "prompt": user_prompt,
                    "intent": action.value,
                    "response": response,
                    "tickets": self._last_search_results
                }
            
            elif action == ActionType.CREATE:
                # Extract ticket details from prompt using AI
                extract_prompt = f"""Extract ticket details from this request:
"{user_prompt}"

Return a JSON object with:
- summary: brief ticket title
- description: detailed description
- issue_type: Story, Bug, or Task
- priority: Low, Medium, High, or Critical

JSON only, no other text:"""
                
                extracted = await self.ai_service.call_genai(
                    prompt=extract_prompt,
                    temperature=0.1,
                    max_tokens=500
                )
                
                # Parse the extracted JSON
                try:
                    # Clean up the response
                    json_match = re.search(r'\{[^}]+\}', extracted, re.DOTALL)
                    if json_match:
                        ticket_data = json.loads(json_match.group())
                    else:
                        ticket_data = json.loads(extracted)
                    
                    result = await self._create_jira_issue(
                        summary=ticket_data.get('summary', 'New Ticket'),
                        description=ticket_data.get('description', user_prompt),
                        issue_type=ticket_data.get('issue_type', 'Story'),
                        priority=ticket_data.get('priority', 'Medium')
                    )
                    
                    return {
                        "success": "✅" in result,
                        "prompt": user_prompt,
                        "intent": action.value,
                        "response": result,
                        "tickets": []
                    }
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "prompt": user_prompt,
                        "intent": action.value,
                        "response": "Could not extract ticket details. Please provide a clearer description.",
                        "tickets": []
                    }
            
            elif action == ActionType.UPDATE and ticket_key:
                # Extract update details from prompt
                extract_prompt = f"""Extract update details from this request for ticket {ticket_key}:
"{user_prompt}"

Return a JSON object with any of these fields to update:
- status: new status (To Do, In Progress, Done, etc.)
- priority: new priority
- comment: comment to add

JSON only, no other text:"""
                
                extracted = await self.ai_service.call_genai(
                    prompt=extract_prompt,
                    temperature=0.1,
                    max_tokens=500
                )
                
                try:
                    json_match = re.search(r'\{[^}]+\}', extracted, re.DOTALL)
                    if json_match:
                        update_data = json.loads(json_match.group())
                    else:
                        update_data = json.loads(extracted)
                    
                    result = await self._update_jira_issue(
                        ticket_key=ticket_key,
                        fields={},
                        status=update_data.get('status'),
                        comment=update_data.get('comment')
                    )
                    
                    return {
                        "success": "✅" in result,
                        "prompt": user_prompt,
                        "intent": action.value,
                        "response": result,
                        "tickets": []
                    }
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "prompt": user_prompt,
                        "intent": action.value,
                        "response": "Could not extract update details. Please be more specific.",
                        "tickets": []
                    }
            
            elif action == ActionType.GET_DETAILS and ticket_key:
                result = await self._get_ticket_details(ticket_key)
                return {
                    "success": True,
                    "prompt": user_prompt,
                    "intent": action.value,
                    "response": result,
                    "tickets": []
                }
            
            else:
                # Default search
                result = await self._search_tickets(user_prompt)
                return {
                    "success": True,
                    "prompt": user_prompt,
                    "intent": "search",
                    "response": result,
                    "tickets": self._last_search_results
                }
                
        except Exception as e:
            log_error(f"Direct processing error: {e}", "jira_agent", e)
            return {
                "success": False,
                "prompt": user_prompt,
                "intent": action.value,
                "response": f"Error: {str(e)}",
                "tickets": []
            }
    
    async def _run_agent(self, query: str) -> Dict[str, Any]:
        """Run the LangChain agent asynchronously."""
        import asyncio
        
        # The agent executor needs to run in sync context
        def run_sync():
            return self.agent.invoke({"input": query})
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_sync)
        
        return result


# Global instance
jira_agent = JiraAgent()
