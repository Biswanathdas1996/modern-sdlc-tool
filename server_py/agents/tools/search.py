"""Search logic for JIRA tickets."""
from typing import List, Dict, Any, Optional
import re

from core.logging import log_info, log_error, log_debug


async def generate_jql_from_query(ai_service, query: str, project_key: Optional[str] = None) -> Optional[str]:
    """Use LLM to generate JQL from natural language query.
    
    Args:
        ai_service: AI service instance for LLM calls
        query: Natural language search query
        project_key: Optional JIRA project key to scope the search
        
    Returns:
        JQL query string or None if generation fails
    """
    try:
        log_info(f"Generating JQL for: {query}", "jql_generator")
        
        prompt = f"""Convert this natural language query to JIRA Query Language (JQL).

Query: "{query}"

JQL Syntax Reference:
- Field operators: =, !=, ~, !~, >, <, >=, <=, IN, NOT IN, IS, IS NOT
- Text search: summary ~ "keyword" or text ~ "keyword" (contains)
- Issue types: type = Bug, type = Story, type = Task, type = Epic, type = "Sub-task"
- Status: status = "In Progress", status = Done, status = "To Do", status IN ("In Progress", "In Review")
- Priority: priority = High, priority = Critical, priority = Medium, priority = Low
- Labels: labels = "bug-fix", labels IN ("urgent", "frontend")
- Components: component = "Backend", component IN ("API", "Database")
- Assignee: assignee = currentUser(), assignee = "John Doe", assignee IS EMPTY
- Reporter: reporter = currentUser(), reporter = "Jane Doe"
- Date functions: created >= -7d (last 7 days), created >= startOfWeek(), updated >= -1w
- Sprint: sprint IN openSprints(), sprint = "Sprint 5"
- Resolution: resolution = Unresolved, resolution IS EMPTY
- Logical operators: AND, OR, NOT
- Ordering: ORDER BY created DESC, ORDER BY priority ASC

Examples:
- "high priority bugs" -> type = Bug AND priority IN (High, Critical) ORDER BY priority DESC
- "my open tasks" -> assignee = currentUser() AND resolution = Unresolved AND type = Task
- "bugs created this week" -> type = Bug AND created >= startOfWeek() ORDER BY created DESC
- "stories in progress" -> type = Story AND status = "In Progress"
- "unassigned tickets" -> assignee IS EMPTY AND resolution = Unresolved
- "issues with label frontend" -> labels = "frontend"
- "critical issues updated recently" -> priority = Critical AND updated >= -3d
- "epics in backlog" -> type = Epic AND status = Backlog

Rules:
1. Always include ORDER BY for better results (prefer created DESC or priority DESC)
2. Use proper quoting for values with spaces
3. Use resolution = Unresolved for open issues
4. Be generous with interpretation - if user mentions "bugs", include type = Bug
5. If query mentions time ("recent", "this week", "today"), use appropriate date functions
6. For vague queries, create a broad but sensible JQL

Return ONLY the JQL query, nothing else. No explanation, no markdown."""

        jql = await ai_service.call_genai(
            prompt=prompt,
            temperature=0.1,
            max_tokens=200
        )
        
        # Clean the response
        jql = jql.strip().strip('`').strip('"').strip("'")
        
        # Remove any "JQL:" prefix if present
        if jql.lower().startswith('jql:'):
            jql = jql[4:].strip()
        
        # Add project filter if provided and not already present
        if project_key and 'project' not in jql.lower():
            # Handle ORDER BY - it must come at the end, outside parentheses
            if 'order by' in jql.lower():
                order_idx = jql.lower().index('order by')
                query_part = jql[:order_idx].strip()
                order_part = jql[order_idx:].strip()
                jql = f"project = {project_key} AND ({query_part}) {order_part}"
            else:
                jql = f"project = {project_key} AND ({jql})"
        elif project_key:
            # Project is mentioned, ensure it's using the right key
            pass
            
        log_info(f"Generated JQL: {jql}", "jql_generator")
        return jql
        
    except Exception as e:
        log_error(f"JQL generation failed: {e}", "jql_generator", e)
        return None


async def search_with_jql(jira_service, ai_service, query: str, project_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search JIRA using LLM-generated JQL.
    
    Args:
        jira_service: JIRA service instance
        ai_service: AI service for JQL generation
        query: Natural language search query
        project_key: Optional project key to scope search
        
    Returns:
        List of matching tickets
    """
    try:
        # Generate JQL from natural language
        jql = await generate_jql_from_query(ai_service, query, project_key)
        
        if not jql:
            log_info("JQL generation failed, falling back to keyword search", "search")
            return await search_jira_tickets(jira_service, query)
        
        # Execute JQL search
        try:
            tickets = await jira_service.search_with_jql(jql)
            log_info(f"JQL search returned {len(tickets)} results", "search")
            return tickets
        except Exception as jql_error:
            log_error(f"JQL execution failed: {jql_error}, falling back to keyword search", "search")
            return await search_jira_tickets(jira_service, query)
            
    except Exception as e:
        log_error(f"Search error: {e}", "search", e)
        return await search_jira_tickets(jira_service, query)


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
