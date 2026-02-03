# JIRA Agent with PwC GenAI

An AI-powered agent that searches and finds related JIRA tickets based on natural language prompts using PwC's GenAI service.

## Overview

The JIRA Agent uses PwC GenAI to intelligently search through JIRA tickets and find relevant matches based on user prompts. It understands natural language queries and performs intelligent matching to find the most relevant tickets.

## Features

- **Natural Language Search**: Search for JIRA tickets using natural language queries
- **AI-Powered Matching**: Uses PwC GenAI to understand context and find relevant tickets
- **Detailed Results**: Returns ticket keys, summaries, descriptions, status, and priority
- **Relevance Scoring**: Automatically ranks tickets by relevance to your query
- **Smart Analysis**: AI provides explanations of why tickets are relevant

## Setup

### Prerequisites

1. **Environment Variables**: Set the following in your `.env` file:

```bash
# PwC GenAI Configuration
PWC_GENAI_API_KEY=your_api_key
PWC_GENAI_BEARER_TOKEN=your_bearer_token
PWC_GENAI_ENDPOINT_URL=https://your-pwc-genai-endpoint.com/api

# JIRA Configuration
JIRA_EMAIL=your_email@example.com
JIRA_API_TOKEN=your_jira_api_token
JIRA_INSTANCE_URL=your_instance.atlassian.net
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
```

2. **Install Dependencies**:

```bash
pip install -r requirements.txt
```

No additional packages required beyond the existing requirements.

## Usage

### As an API Endpoint

Use the REST API endpoint to search for tickets:

**POST** `/api/v1/jira-agent/search`

**Request Body**:
```json
{
  "prompt": "Find all tickets related to user authentication",
  "max_results": 10
}
```

**Response**:
```json
{
  "success": true,
  "prompt": "Find all tickets related to user authentication",
  "response": "Based on your query, I found 3 highly relevant tickets:\n\n1. [KAN-123] Implement user login feature\n   This ticket is relevant because it directly addresses user authentication...\n\n2. [KAN-124] Fix password reset bug\n   This is related to the authentication flow...",
  "tickets": [
    {
      "key": "KAN-123",
      "summary": "Implement user login feature",
      "description": "Add authentication system...",
      "status": "In Progress",
      "priority": "High",
      "labels": ["authentication", "security"]
    }
  ]
}
```

### Programmatic Usage

```python
from agents.jira_agent import jira_agent
import asyncio

async def search_tickets():
    result = await jira_agent.find_related_tickets(
        "Find tickets about database performance issues"
    )
    
    if result['success']:
        print(result['response'])
        print(f"\nFound {len(result['tickets'])} tickets")
    else:
        print(f"Error: {result['error']}")

asyncio.run(search_tickets())
```

### Example Queries

Here are some example prompts you can use:

1. **Feature Search**:
   - "Find all tickets related to user authentication"
   - "Show me API development tickets"
   - "What tickets are about payment integration?"

2. **Bug Search**:
   - "Find all bug tickets related to the database"
   - "Show me critical bugs"
   - "What are the open security issues?"

3. **Status-based Search**:
   - "Find all in-progress tickets"
   - "Show me completed user stories"
   - "What tickets are blocked?"

4. **Technical Search**:
   - "Find tickets about microservices architecture"
   - "Show me frontend React tickets"
   - "What tickets involve Docker or containers?"

## How It Works

1. **User Prompt**: You provide a natural language query
2. **Keyword Search**: The agent performs an initial keyword-based search to find potentially relevant tickets
3. **Relevance Scoring**: Tickets are scored based on keyword matches in summary, description, and labels
4. **AI Analysis**: PwC GenAI analyzes the tickets and provides intelligent insights about relevance
5. **Results**: Returns ranked tickets with AI-generated explanations

### Relevance Scoring

The initial filtering uses a scoring system:
- +3 points: Query term found in ticket summary
- +2 points: Query term found in ticket description
- +1 point: Query term found in ticket labels

Results are then analyzed by PwC GenAI for deeper semantic understanding.

## API Documentation

### Search for Related Tickets

**POST** `/api/v1/jira-agent/search`

Search for JIRA tickets based on a natural language prompt.

**Request Parameters**:
- `prompt` (string, required): The search query
- `max_results` (integer, optional): Maximum number of results (default: 10)

**Response Fields**:
- `success` (boolean): Whether the search was successful
- `prompt` (string): The original search query
- `response` (string): AI-generated analysis of relevant tickets
- `tickets` (array): List of relevant ticket objects
- `error` (string, optional): Error message if search failed

### Health Check

**GET** `/api/v1/jira-agent/health`

Returns the health status of the JIRA agent service.

**Response**:
```json
{
  "status": "healthy",
  "service": "jira-agent"
}
```

## Architecture

```
agents/
├── __init__.py           # Module initialization
├── jira_agent.py         # Main agent implementation with PwC GenAI
├── example_usage.py      # Usage examples
└── README.md            # This file

api/v1/
└── jira_agent.py        # FastAPI endpoints
```

### Key Components

1. **JiraAgent Class**: Main agent class that orchestrates the search
2. **Search Algorithm**:
   - Keyword-based initial filtering
   - Relevance scoring
   - PwC GenAI analysis for semantic understanding
3. **JIRA Service**: Leverages existing JIRA service for API calls
4. **PwC GenAI Integration**: Uses AI service for intelligent analysis

## Error Handling

The agent handles various error scenarios:
- Missing PwC GenAI credentials
- Missing JIRA credentials
- API rate limits
- Network errors
- Invalid queries
- No matching results

Errors are logged and returned in a structured format.

## Advantages of PwC GenAI Integration

- **Enterprise-grade**: Built on PwC's secure GenAI infrastructure
- **No External Dependencies**: No need for third-party AI services like OpenAI
- **Consistent**: Uses the same AI service as the rest of the application
- **Customizable**: Temperature and token settings can be adjusted
- **Secure**: All data stays within PwC's infrastructure

## Limitations

- Requires active JIRA credentials
- Requires PwC GenAI access
- Search is limited to the configured JIRA project
- Maximum of 10 results returned per search (configurable)
- Relevance depends on ticket content quality

## Future Enhancements

- [ ] Add caching for frequently searched queries
- [ ] Support for advanced JQL queries
- [ ] Multi-project search capability
- [ ] Vector embeddings for semantic search
- [ ] Conversation history for follow-up questions
- [ ] Custom relevance scoring algorithms

## Troubleshooting

### "PwC GenAI credentials not configured"
- Ensure `PWC_GENAI_API_KEY`, `PWC_GENAI_BEARER_TOKEN`, and `PWC_GENAI_ENDPOINT_URL` are set in your `.env` file

### "JIRA credentials not configured"
- Ensure `JIRA_EMAIL` and `JIRA_API_TOKEN` are set in your `.env` file

### "No JIRA tickets found"
- Check that your JIRA project has stories
- Verify `JIRA_PROJECT_KEY` is correct
- Try using different search terms

### "PwC GenAI API Error"
- Verify your PwC GenAI credentials are valid
- Check network connectivity to the GenAI endpoint
- Ensure your API key has sufficient permissions

## License

Part of the Modern SDLC Tool project.
