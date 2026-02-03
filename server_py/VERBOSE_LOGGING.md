# Verbose Logging Configuration

## What Was Changed

I've enabled detailed verbose console logging throughout the JIRA agent execution. Here's what was updated:

### 1. **Core Logging Configuration** ([core/logging.py](server_py/core/logging.py))
   - Changed default log level from `INFO` to `DEBUG`
   - Added logger name to log format for better traceability
   - Added new `log_debug()` function for debug-level messages

### 2. **JIRA Agent** ([agents/jira_agent.py](server_py/agents/jira_agent.py))
   - Added `VerboseConsoleHandler` callback to AgentExecutor for detailed step-by-step output
   - Added debug logging for:
     - Tool invocations (search, get details, list tickets)
     - Ticket search and scoring process
     - AI analysis steps
     - Response generation

### 3. **JIRA Service** ([services/jira_service.py](server_py/services/jira_service.py))
   - Added debug logging for API requests
   - Logs JQL queries and response status codes
   - Shows number of issues retrieved

### 4. **AI Service** ([services/ai_service.py](server_py/services/ai_service.py))
   - Added debug logging for GenAI API calls
   - Shows request parameters (temperature, max_tokens)
   - Logs response structure and status

## What You'll See Now

When the agent executes, you'll see detailed console output including:

### 🎨 Emoji Indicators:
- `🚀` - Agent starting
- `🔧` - Tool execution
- `💭` - LLM (AI) calls
- `🤖` - Agent actions
- `✅` - Successful completion
- `❌` - Errors

### 📋 Log Levels:
- `[DEBUG]` - Detailed internal operations
- `[INFO]` - General information
- `[WARNING]` - Warnings
- `[ERROR]` - Errors with stack traces

### 🔍 Detailed Information:
1. **Search Process**
   - Query being processed
   - Number of JIRA stories fetched
   - Relevance scoring details
   - Top matching tickets

2. **Tool Calls**
   - Which tool is being invoked
   - Input parameters
   - Output results (truncated if long)

3. **AI Interactions**
   - When AI is called
   - Request parameters
   - Response status

4. **HTTP Requests**
   - API endpoints being called
   - Response status codes
   - Data received

## How to Use

### Option 1: Run the Test Script
```powershell
cd server_py
python test_agent_verbose.py
```

### Option 2: Start the Full Application
```powershell
cd server_py
python main.py
```

Then make API requests to `/api/v1/jira-agent/search` and watch the console.

### Option 3: Use the REST Client
1. Open [rest_client/jira_agent.rest](server_py/rest_client/jira_agent.rest)
2. Send a POST request
3. Watch the server console for detailed logs

## Example Output

```
================================================================================
🚀 JIRA AGENT STARTING
================================================================================
Query: login authentication user stories

02:34:12 PM [DEBUG] [docugen] [jira_agent] Tool called: search_jira_tickets with query='login authentication'

🔧 [STEP 1] Searching JIRA tickets...
02:34:12 PM [INFO] [docugen] [jira_agent] Searching JIRA tickets with query: login authentication
02:34:12 PM [DEBUG] [docugen] [jira_agent] Fetching all JIRA stories from service
02:34:12 PM [DEBUG] [docugen] [jira_service] Fetching JIRA stories from yourinstance.atlassian.net
02:34:12 PM [DEBUG] [docugen] [jira_service] JQL query: project = PROJ AND issuetype = Story ORDER BY created DESC
02:34:13 PM [DEBUG] [docugen] [jira_service] JIRA API response status: 200
02:34:13 PM [DEBUG] [docugen] [jira_service] Received 15 issues from JIRA
02:34:13 PM [INFO] [docugen] [jira] Fetched 15 JIRA stories
02:34:13 PM [DEBUG] [docugen] [jira_agent] Retrieved 15 stories from JIRA
02:34:13 PM [DEBUG] [docugen] [jira_agent] Scoring tickets against query: 'login authentication'
02:34:13 PM [DEBUG] [docugen] [jira_agent] Found 8 relevant tickets, returning top 10
02:34:13 PM [DEBUG] [docugen] [jira_agent] Top ticket: PROJ-123 (score: 8)

✅ Found 8 relevant tickets

🔧 [STEP 2] Analyzing tickets with AI...
02:34:13 PM [DEBUG] [docugen] [jira_agent] Calling AI for intelligent summary
02:34:13 PM [INFO] [docugen] [ai] Calling PwC GenAI (prompt length: 1234 chars)
02:34:13 PM [DEBUG] [docugen] [ai] AI parameters: temp=0.3, max_tokens=2000
02:34:13 PM [DEBUG] [docugen] [ai] Using model: vertex_ai.gemini-2.0-flash
02:34:13 PM [DEBUG] [docugen] [ai] Sending POST request to https://genai.api.pwc.com/...
02:34:15 PM [DEBUG] [docugen] [ai] AI API response status: 200
02:34:15 PM [DEBUG] [docugen] [ai] AI response structure: ['choices', 'model', 'usage']
02:34:15 PM [INFO] [docugen] [ai] PwC GenAI response received successfully
02:34:15 PM [DEBUG] [docugen] [jira_agent] AI response received: 456 chars

✅ AI analysis complete

================================================================================
✅ JIRA AGENT COMPLETED
================================================================================
```

## Adjusting Verbosity

If you want **less** verbose output:

In [core/logging.py](server_py/core/logging.py), change:
```python
def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
```
to:
```python
def setup_logging(level: int = logging.INFO) -> logging.Logger:
```

## Benefits

1. **Transparency** - See exactly what the agent is doing at each step
2. **Debugging** - Quickly identify where issues occur
3. **Performance** - Monitor API call timing and data flow
4. **Learning** - Understand how LangChain agents work internally
5. **Troubleshooting** - Detailed error messages with context
