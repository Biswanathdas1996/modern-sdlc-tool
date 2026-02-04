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
    SUBTASK = "subtask"
    LINK = "link"
    SEARCH_AND_UPDATE = "search_and_update"
    GET_DETAILS = "get_details"
    ISSUE_REPORT = "issue_report"
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
    
    # Detect action patterns (with common typo variations)
    create_patterns = [
        'create', 'crete', 'creat',  # typos
        'add', 'ad',
        'new ticket', 'new task', 'new bug', 'new story', 'new issue',
        'make a', 'make an',
        'open a ticket', 'open ticket', 'raise a', 'raise ticket',
        'file a', 'submit a', 'log a'
    ]
    update_patterns = ['update', 'change', 'modify', 'set status', 'mark as', 'move to', 'transition']
    search_patterns = ['find', 'search', 'show', 'list', 'get', 'what are', 'which tickets', 'show me', 'give me']
    chained_patterns = ['and update', 'and change', 'then update', 'then mark', 'and mark']
    subtask_patterns = ['subtask', 'sub-task', 'sub task', 'child task', 'add subtask', 'create subtask', 'add sub-task']
    link_patterns = ['link', 'connect', 'relate', 'link to', 'relates to', 'blocks', 'is blocked by', 'duplicate']
    
    # Problem description patterns - these suggest the user is reporting an issue
    problem_patterns = [
        "can't see", "cannot see", "can't find", "cannot find",
        "not working", "doesn't work", "does not work", "isn't working",
        "not loading", "won't load", "will not load",
        "broken", "error", "issue with", "problem with",
        "missing", "disappeared", "gone"
    ]
    
    is_search = any(p in prompt_lower for p in search_patterns)
    is_create = any(p in prompt_lower for p in create_patterns)
    is_update = any(p in prompt_lower for p in update_patterns)
    is_chained = any(p in prompt_lower for p in chained_patterns)
    is_subtask = any(p in prompt_lower for p in subtask_patterns)
    is_link = any(p in prompt_lower for p in link_patterns)
    is_problem_description = any(p in prompt_lower for p in problem_patterns)
    
    # Additional check: if prompt contains words like "new" + "ticket/bug/task/story"
    # even if misspelled, treat as create
    has_new = 'new' in prompt_lower
    has_ticket_word = any(word in prompt_lower for word in ['ticket', 'tickt', 'tkt', 'bug', 'task', 'story', 'issue'])
    if has_new and has_ticket_word and not is_search:
        is_create = True
    
    # Detect ticket key in prompt
    ticket_key_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
    specific_ticket = ticket_key_match.group(1) if ticket_key_match else None
    
    if is_subtask:
        return {"action": ActionType.SUBTASK, "ticket_key": specific_ticket}
    elif is_link:
        # Allow LINK intent even without ticket keys - info gathering will prompt for them
        return {"action": ActionType.LINK, "ticket_key": specific_ticket}
    elif is_search and is_chained:
        return {"action": ActionType.SEARCH_AND_UPDATE, "ticket_key": specific_ticket}
    elif is_create:
        return {"action": ActionType.CREATE, "ticket_key": specific_ticket}
    elif is_update and specific_ticket:
        return {"action": ActionType.UPDATE, "ticket_key": specific_ticket}
    elif specific_ticket and not is_search:
        return {"action": ActionType.GET_DETAILS, "ticket_key": specific_ticket}
    elif is_search:
        return {"action": ActionType.SEARCH, "ticket_key": specific_ticket}
    elif is_problem_description and not is_search and not is_create:
        # If user is describing a problem without explicit commands,
        # use ISSUE_REPORT to search for related tickets first, then ask what to do
        return {"action": ActionType.ISSUE_REPORT, "ticket_key": specific_ticket}
    else:
        return {"action": ActionType.UNKNOWN, "ticket_key": specific_ticket}
