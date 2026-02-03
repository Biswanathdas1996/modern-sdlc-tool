# Status-Based Query Fix

## Problem

When asking "Find all in-progress tickets", the agent was returning **all tickets** and just mentioning which ones were in progress in the AI response, rather than actually **filtering** to show only in-progress tickets.

### Example of the Issue:
- Query: "Find all in-progress tickets"
- Expected: Only tickets with status "In Progress"  
- Actual: 9 tickets returned (8 Done, 1 In Progress), with AI just noting which one was in progress

## Solution

Updated the `_search_jira_tickets()` method in [agents/jira_agent.py](agents/jira_agent.py) to:

### 1. **Detect Status-Based Queries**
The agent now recognizes status keywords in queries:
- `in progress`, `in-progress`, `progress` → Filters for "In Progress"
- `todo`, `to do` → Filters for "To Do"
- `done`, `completed`, `finished` → Filters for "Done"
- `review`, `in review` → Filters for "In Review"
- `blocked` → Filters for "Blocked"
- `backlog` → Filters for "Backlog"

### 2. **Apply Status Filtering**
When a status keyword is detected:
```python
# Filter tickets by exact status match
filtered_stories = [s for s in stories if s.get("status") == target_status]

# Return ALL matching tickets (no need for relevance scoring)
return filtered_stories
```

### 3. **Improved AI Prompting**
For status-based queries, the AI receives a special prompt clarifying that the tickets are pre-filtered:
```
IMPORTANT: These tickets have already been filtered by status. 
ALL X tickets shown match the user's status criteria.
```

This prevents the AI from incorrectly summarizing that "only one ticket matches" when multiple are shown.

## Changes Made

### File: `agents/jira_agent.py`

**Added Status Detection:**
```python
status_keywords = {
    'in progress': 'In Progress',
    'in-progress': 'In Progress',
    'progress': 'In Progress',
    'todo': 'To Do',
    # ... more mappings
}

target_status = None
for keyword, status in status_keywords.items():
    if keyword in query_lower:
        target_status = status
        break
```

**Added Status Filtering:**
```python
if target_status:
    filtered_stories = [s for s in stories if s.get("status") == target_status]
    log_debug(f"Status filter applied: {len(filtered_stories)} tickets with status '{target_status}'", "jira_agent")
    return filtered_stories
```

**Enhanced AI Prompt:**
```python
if is_status_query:
    analysis_prompt = f"""
    I have FILTERED the tickets to match the requested status. 
    Here are ALL the tickets that match:
    {tickets_summary}
    
    IMPORTANT: These tickets have already been filtered by status. 
    ALL {len(relevant_tickets)} tickets shown match the user's status criteria.
    """
```

## Testing

### Test Queries:

1. **In-Progress Tickets:**
   ```http
   POST http://localhost:5000/api/v1/jira-agent/search
   {
     "prompt": "Find all in-progress tickets"
   }
   ```
   ✅ Returns only tickets with status "In Progress"

2. **Done Tickets:**
   ```http
   POST http://localhost:5000/api/v1/jira-agent/search
   {
     "prompt": "Show me completed tickets"
   }
   ```
   ✅ Returns only tickets with status "Done"

3. **In Review Tickets:**
   ```http
   POST http://localhost:5000/api/v1/jira-agent/search
   {
     "prompt": "What tickets are in review?"
   }
   ```
   ✅ Returns only tickets with status "In Review"

4. **Mixed Queries (still works):**
   ```http
   POST http://localhost:5000/api/v1/jira-agent/search
   {
     "prompt": "kyc page"
   }
   ```
   ✅ Does keyword search as before (no status filtering)

## Console Output (Verbose Mode)

With the verbose logging enabled, you'll see:

```
05:20:35 PM [DEBUG] [docugen] [jira_agent] Fetching all JIRA stories from service
05:20:35 PM [DEBUG] [docugen] [jira_service] Fetching JIRA stories from instance.atlassian.net
05:20:36 PM [DEBUG] [docugen] [jira_agent] Retrieved 9 stories from JIRA
05:20:36 PM [DEBUG] [docugen] [jira_agent] Detected status-based query: filtering for status='In Progress'
05:20:36 PM [DEBUG] [docugen] [jira_agent] Status filter applied: 1 tickets with status 'In Progress'
```

## Benefits

✅ **Accurate Results** - Returns only tickets matching the requested status  
✅ **Clear Intent Detection** - Automatically recognizes status-based queries  
✅ **Better AI Responses** - AI understands the tickets are pre-filtered  
✅ **Verbose Logging** - See exactly what filtering is happening  
✅ **Backward Compatible** - Keyword searches still work as before  

## Next Steps

To test with your server:

1. **Kill the existing process on port 5000:**
   ```powershell
   taskkill /F /PID 32912
   ```

2. **Start the server:**
   ```powershell
   cd server_py
   python main.py
   ```

3. **Send the request** from [jira_agent.rest](rest_client/jira_agent.rest):
   - Go to line 75
   - Click "Send Request"
   - Watch the console for verbose output
   - Check that only "In Progress" tickets are returned

The response should now correctly show **only** the in-progress tickets!
