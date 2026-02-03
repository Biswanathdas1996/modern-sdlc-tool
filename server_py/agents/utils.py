"""Utility functions for JIRA agent operations."""
import re
from typing import Dict, Any
from enum import Enum

from core.logging import log_info, log_error


class ActionType(Enum):
    """Types of actions the agent can perform."""
    SEARCH = "search"
    CREATE = "create"
    UPDATE = "update"
    SEARCH_AND_UPDATE = "search_and_update"
    GET_DETAILS = "get_details"
    UNKNOWN = "unknown"


def handle_parsing_error(error: Exception) -> str:
    """Handle LangChain agent parsing errors gracefully.
    
    Args:
        error: Exception raised by the agent
        
    Returns:
        Extracted answer or fallback message
    """
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
        lines = error_msg.split('\n')
        for i, line in enumerate(lines):
            if 'Final Answer:' in line and i + 1 < len(lines):
                answer_line = lines[i].split('Final Answer:')[-1].strip()
                if answer_line:
                    return answer_line
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    
    return "I encountered an issue processing the response. Let me try a simpler approach."


def analyze_intent(user_prompt: str) -> Dict[str, Any]:
    """Analyze user intent to determine the action type.
    
    Args:
        user_prompt: User's natural language query
        
    Returns:
        Dictionary with detected action type and ticket key (if found)
    """
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
