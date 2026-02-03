"""Search logic for JIRA tickets."""
from typing import List, Dict, Any

from core.logging import log_info, log_error, log_debug


async def search_jira_tickets(jira_service, query: str) -> List[Dict[str, Any]]:
    """Search for JIRA tickets based on query.
    
    Args:
        jira_service: JiraService instance
        query: Search query string
        
    Returns:
        List of relevant JIRA tickets
    """
    try:
        log_info(f"Searching JIRA tickets with query: {query}", "jira_agent")
        log_debug(f"Fetching all JIRA stories from service", "jira_agent")
        
        # Fetch all JIRA stories
        stories = await jira_service.get_jira_stories()
        
        if not stories:
            log_debug("No stories found from JIRA service", "jira_agent")
            return []
        
        log_debug(f"Retrieved {len(stories)} stories from JIRA", "jira_agent")
        
        # Detect if this is an issue type query
        query_lower = query.lower()
        issue_type_keywords = {
            'bug': 'Bug',
            'bugs': 'Bug',
            'story': 'Story',
            'stories': 'Story',
            'task': 'Task',
            'tasks': 'Task',
            'sub-task': 'Sub-task',
            'subtask': 'Sub-task',
            'epic': 'Epic'
        }
        
        target_issue_type = None
        for keyword, issue_type in issue_type_keywords.items():
            if keyword in query_lower:
                target_issue_type = issue_type
                log_debug(f"Detected issue type query: filtering for type='{target_issue_type}'", "jira_agent")
                break
        
        # Detect if this is a status-based query
        status_keywords = {
            'in progress': 'In Progress',
            'in-progress': 'In Progress',
            'progress': 'In Progress',
            'todo': 'To Do',
            'to do': 'To Do',
            'done': 'Done',
            'completed': 'Done',
            'finished': 'Done',
            'review': 'In Review',
            'in review': 'In Review',
            'blocked': 'Blocked',
            'backlog': 'Backlog'
        }
        
        target_status = None
        for keyword, status in status_keywords.items():
            if keyword in query_lower:
                target_status = status
                log_debug(f"Detected status-based query: filtering for status='{target_status}'", "jira_agent")
                break
        
        # Apply filters (issue type and/or status)
        filtered_stories = stories
        
        if target_issue_type:
            filtered_stories = [s for s in filtered_stories if s.get("issueType") == target_issue_type]
            log_debug(f"Issue type filter applied: {len(filtered_stories)} tickets with type '{target_issue_type}'", "jira_agent")
        
        if target_status:
            filtered_stories = [s for s in filtered_stories if s.get("status") == target_status]
            log_debug(f"Status filter applied: {len(filtered_stories)} tickets with status '{target_status}'", "jira_agent")
        
        # If we have specific filters and results, return them
        if (target_issue_type or target_status) and filtered_stories:
            log_debug(f"Returning {len(filtered_stories)} filtered tickets", "jira_agent")
            return filtered_stories
        
        # If filters were applied but no results, return empty
        if (target_issue_type or target_status) and not filtered_stories:
            log_debug(f"No tickets found matching filters", "jira_agent")
            return []
        
        # Otherwise, do keyword-based search on all tickets
        stories_to_search = filtered_stories if (target_issue_type or target_status) else stories
        
        log_debug(f"Scoring tickets against query: '{query_lower}'", "jira_agent")
        
        relevant_tickets = []
        for story in stories_to_search:
            score = 0
            summary = story.get("summary", "").lower()
            description = story.get("description", "").lower()
            labels = [label.lower() for label in story.get("labels", [])]
            status = story.get("status", "").lower()
            
            # Simple relevance scoring
            query_terms = query_lower.split()
            for term in query_terms:
                if term in summary:
                    score += 3
                if term in description:
                    score += 2
                if term in ' '.join(labels):
                    score += 1
                if term in status:
                    score += 2
            
            if score > 0:
                relevant_tickets.append({
                    "story": story,
                    "score": score
                })
        
        # Sort by relevance score
        relevant_tickets.sort(key=lambda x: x["score"], reverse=True)
        
        log_debug(f"Found {len(relevant_tickets)} relevant tickets, returning top 10", "jira_agent")
        if relevant_tickets:
            log_debug(f"Top ticket: {relevant_tickets[0]['story']['key']} (score: {relevant_tickets[0]['score']})", "jira_agent")
        
        # Return top 10 most relevant
        return [item["story"] for item in relevant_tickets[:10]]
        
    except Exception as e:
        log_error(f"Error searching JIRA tickets", "jira_agent", e)
        return []
