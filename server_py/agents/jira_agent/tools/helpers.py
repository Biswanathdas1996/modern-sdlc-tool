"""Helper functions for JIRA agent operations."""
from typing import List, Dict, Any


def format_tickets_for_agent(tickets: List[Dict[str, Any]]) -> str:
    """Format tickets data for agent tool output.
    
    Args:
        tickets: List of JIRA ticket dictionaries
        
    Returns:
        Formatted string representation of tickets
    """
    formatted = []
    for idx, ticket in enumerate(tickets, 1):
        formatted.append(
            f"[{ticket['key']}] {ticket['summary']}\n"
            f"Status: {ticket['status']} | Priority: {ticket['priority']}\n"
            f"Labels: {', '.join(ticket.get('labels', [])) if ticket.get('labels') else 'None'}\n"
            f"Description: {ticket['description'][:200]}{'...' if len(ticket['description']) > 200 else ''}\n"
        )
    return '\n'.join(formatted)
