"""
Information gathering utilities for intelligent Jira agent.
Detects missing information and generates prompts for users with contextual awareness.
"""
from typing import Dict, Any, List, Optional
import re
from .conversation_manager import InfoRequest
from .utils import ActionType


def _add_context_hint(description: str, context_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Add contextual hints to info requests based on available knowledge.
    Keep hints minimal and unobtrusive.
    """
    # Removed verbose hints - context is used intelligently in background
    return description


def validate_create_ticket_data(
    user_prompt: str, 
    collected_data: Dict[str, Any],
    context_data: Optional[Dict[str, Any]] = None
) -> tuple[bool, List[InfoRequest]]:
    """
    Validate if we have all necessary information to create a ticket.
    Ask for information ONE field at a time for better UX.
    
    Args:
        user_prompt: User's original query
        collected_data: Data collected so far
        context_data: Optional context from KB and existing tickets
        
    Returns:
        Tuple of (is_complete, missing_fields)
    """
    missing = []
    
    # STRICT validation - ask for fields in order, one at a time
    # This creates a conversational flow
    
    # 1. Issue Type (ask first to understand context)
    if not collected_data.get("issue_type"):
        missing.append(InfoRequest(
            field="issue_type",
            description="What type of ticket would you like to create?",
            options=["Bug", "Story", "Task", "Epic"]
        ))
        return False, missing  # Return immediately to ask one at a time
    
    # 2. Summary/Title
    if not collected_data.get("summary") or len(collected_data.get("summary", "").strip()) < 5:
        missing.append(InfoRequest(
            field="summary",
            description="Great! Now, what's a brief summary or title for this ticket?\n(Example: 'Fix login button not responding on mobile')"
        ))
        return False, missing
    
    # 3. Description (for context)
    if not collected_data.get("description") or len(collected_data.get("description", "").strip()) < 10:
        missing.append(InfoRequest(
            field="description",
            description="Perfect! Can you provide more details about this? What's happening, steps to reproduce, or expected behavior?"
        ))
        return False, missing
    
    # 4. Priority
    if not collected_data.get("priority"):
        missing.append(InfoRequest(
            field="priority",
            description="How urgent is this?",
            options=["Critical", "High", "Medium", "Low"]
        ))
        return False, missing
    
    # 5. Additional context (optional but useful)
    if not collected_data.get("additional_context_asked"):
        missing.append(InfoRequest(
            field="additional_context",
            description="Any additional information? (Team, affected users, related tickets, etc.)\n\nType 'none' or 'skip' if not applicable."
        ))
        # Mark that we asked this question
        collected_data["additional_context_asked"] = True
        return False, missing
    
    # 6. Final confirmation
    if not collected_data.get("confirmed"):
        summary_msg = f"""📋 **Ready to create ticket:**

**Type:** {collected_data.get('issue_type')}
**Summary:** {collected_data.get('summary')}
**Description:** {collected_data.get('description')}
**Priority:** {collected_data.get('priority')}
{f"**Additional Info:** {collected_data.get('additional_context')}" if collected_data.get('additional_context') and collected_data.get('additional_context').lower() not in ['none', 'skip', 'n/a'] else ''}

Shall I create this ticket? (yes/no)"""
        
        missing.append(InfoRequest(
            field="confirmed",
            description=summary_msg,
            options=["yes", "no"]
        ))
        return False, missing
    
    # Check if user confirmed
    if collected_data.get("confirmed", "").lower() not in ["yes", "y", "confirm", "ok", "sure"]:
        return False, [InfoRequest(
            field="cancelled",
            description="Ticket creation cancelled. Is there anything else I can help you with?"
        )]
    
    return True, []


def validate_update_ticket_data(user_prompt: str, collected_data: Dict[str, Any]) -> tuple[bool, List[InfoRequest]]:
    """
    Validate if we have all necessary information to update a ticket.
    
    Args:
        user_prompt: User's original query
        collected_data: Data collected so far
        
    Returns:
        Tuple of (is_complete, missing_fields)
    """
    missing = []
    
    # Check for ticket key
    if not collected_data.get("ticket_key"):
        missing.append(InfoRequest(
            field="ticket_key",
            description="Please provide the ticket ID (e.g., PROJ-123)"
        ))
    
    # Check for at least one update field
    has_update = any([
        collected_data.get("status"),
        collected_data.get("priority"),
        collected_data.get("summary"),
        collected_data.get("description"),
        collected_data.get("comment")
    ])
    
    if not has_update:
        missing.append(InfoRequest(
            field="update_type",
            description="What would you like to update?",
            options=["Status", "Priority", "Description", "Add Comment"]
        ))
    
    return len(missing) == 0, missing


def validate_search_query(user_prompt: str, collected_data: Dict[str, Any]) -> tuple[bool, List[InfoRequest]]:
    """
    Validate if search query is specific enough.
    
    Args:
        user_prompt: User's original query
        collected_data: Data collected so far
        
    Returns:
        Tuple of (is_complete, missing_fields)
    """
    missing = []
    
    # Check if query is too vague
    vague_terms = ["tickets", "issues", "all", "show", "find", "search"]
    words = user_prompt.lower().split()
    
    if len(words) <= 2 and any(term in words for term in vague_terms):
        missing.append(InfoRequest(
            field="search_criteria",
            description="Please be more specific. What tickets are you looking for? (e.g., 'in progress', 'assigned to me', 'high priority bugs')"
        ))
    
    return len(missing) == 0, missing


def extract_ticket_data_from_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Extract ticket information from user prompt using pattern matching.
    
    Args:
        user_prompt: User's query
        
    Returns:
        Dictionary with extracted data
    """
    extracted = {}
    
    # Extract ticket key (e.g., PROJ-123, ABC-456)
    ticket_key_match = re.search(r'\b([A-Z]+-\d+)\b', user_prompt)
    if ticket_key_match:
        extracted["ticket_key"] = ticket_key_match.group(1)
    
    # Extract priority
    priority_patterns = {
        "critical": ["critical", "urgent", "blocker"],
        "high": ["high", "important"],
        "medium": ["medium", "normal"],
        "low": ["low", "minor", "trivial"]
    }
    for priority, keywords in priority_patterns.items():
        if any(keyword in user_prompt.lower() for keyword in keywords):
            extracted["priority"] = priority.capitalize()
            break
    
    # Extract issue type
    if "bug" in user_prompt.lower() or "defect" in user_prompt.lower():
        extracted["issue_type"] = "Bug"
    elif "story" in user_prompt.lower() or "feature" in user_prompt.lower():
        extracted["issue_type"] = "Story"
    elif "task" in user_prompt.lower():
        extracted["issue_type"] = "Task"
    
    # Extract status
    status_patterns = {
        "To Do": ["to do", "todo", "backlog"],
        "In Progress": ["in progress", "working on", "started"],
        "Done": ["done", "complete", "completed", "finished"],
        "Blocked": ["blocked", "stuck"]
    }
    for status, keywords in status_patterns.items():
        if any(keyword in user_prompt.lower() for keyword in keywords):
            extracted["status"] = status
            break
    
    # Try to extract summary/description from meaningful phrases
    # Skip if it's just a command like "create a bug" or "show tickets"
    command_patterns = [
        r'^(create|make|add|show|list|find|search|get|update)\s+(a\s+)?(bug|task|story|ticket|issue)',
        r'^(show|list|find|get)\s+',
    ]
    is_command_only = any(re.match(pattern, user_prompt.lower()) for pattern in command_patterns)
    
    # If the prompt has substance and isn't just a command, capture it
    if not is_command_only and len(user_prompt.split()) >= 3:
        # Check if it looks like a problem description
        problem_indicators = [
            "can't see", "cannot see", "can't find", "cannot find",
            "not working", "doesn't work", "does not work", "isn't working",
            "not loading", "won't load", "will not load",
            "broken", "error", "issue", "problem", "failed", "failing",
            "missing", "disappeared", "gone"
        ]
        if any(indicator in user_prompt.lower() for indicator in problem_indicators):
            extracted["summary"] = user_prompt.strip()
            extracted["description"] = user_prompt.strip()
    
    return extracted


def merge_user_response(collected_data: Dict[str, Any], user_response: str, missing_field: InfoRequest) -> Dict[str, Any]:
    """
    Intelligently merge user's response into collected data.
    
    Args:
        collected_data: Existing collected data
        user_response: User's response to the question
        missing_field: The field that was being asked about
        
    Returns:
        Updated collected data
    """
    field = missing_field.field
    user_lower = user_response.lower().strip()
    
    # If there are options, try to match intelligently
    if missing_field.options:
        # Try exact match first
        for option in missing_field.options:
            if option.lower() == user_lower:
                collected_data[field] = option
                return collected_data
        
        # Try partial match
        for option in missing_field.options:
            if option.lower() in user_lower or user_lower in option.lower():
                collected_data[field] = option
                return collected_data
        
        # Try number selection (if user typed "1", "2", etc.)
        if user_response.strip().isdigit():
            index = int(user_response.strip()) - 1
            if 0 <= index < len(missing_field.options):
                collected_data[field] = missing_field.options[index]
                return collected_data
    
    # For confirmation fields, handle variations
    if field == "confirmed":
        if user_lower in ["yes", "y", "yeah", "yep", "confirm", "ok", "okay", "sure", "go ahead", "proceed"]:
            collected_data[field] = "yes"
        elif user_lower in ["no", "n", "nope", "cancel", "stop", "abort"]:
            collected_data[field] = "no"
        else:
            collected_data[field] = user_response.strip()
        return collected_data
    
    # Direct assignment for other fields
    collected_data[field] = user_response.strip()
    return collected_data


def generate_info_request_message(missing_fields: List[InfoRequest]) -> str:
    """
    Generate a conversational message requesting missing information.
    Always shows ONE field at a time for better UX.
    
    Args:
        missing_fields: List of missing information fields
        
    Returns:
        Formatted message
    """
    if not missing_fields:
        return ""
    
    # Always take just the first field to keep conversation flowing
    field = missing_fields[0]
    msg = f"💬 {field.description}"
    
    if field.options:
        msg += f"\n\n**Options:**\n"
        for i, option in enumerate(field.options, 1):
            msg += f"  {i}. {option}\n"
    
    return msg
