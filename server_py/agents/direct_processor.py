"""Direct processing fallback for JIRA agent when LangChain agent fails."""
import json
import re
from typing import Dict, Any

from core.logging import log_error
from .utils import ActionType
from .tools import (
    TicketToolsContext,
    search_tickets_tool,
    create_ticket_tool,
    update_ticket_tool,
    get_details_tool,
    format_tickets_for_agent
)


async def direct_process(
    user_prompt: str,
    intent: Dict[str, Any],
    jira_service,
    ai_service,
    context: TicketToolsContext
) -> Dict[str, Any]:
    """
    Direct processing without LangChain agent as a fallback.
    Uses intent analysis to route to appropriate action.
    
    Args:
        user_prompt: User's query
        intent: Analyzed intent with action type and ticket key
        jira_service: JiraService instance
        ai_service: AIService instance
        context: Shared context for storing state
        
    Returns:
        Response dictionary with success status and results
    """
    action = intent.get('action', ActionType.UNKNOWN)
    ticket_key = intent.get('ticket_key')
    
    try:
        if action == ActionType.SEARCH or action == ActionType.UNKNOWN:
            result = await search_tickets_tool(jira_service, context, user_prompt)
            
            # Generate AI analysis of results
            if context.last_search_results:
                tickets_summary = format_tickets_for_agent(context.last_search_results)
                analysis_prompt = f"""You are a JIRA assistant. A user asked: "{user_prompt}"

Here are the JIRA tickets found:

{tickets_summary}

Provide a concise summary including:
1. Number of tickets found
2. Key ticket IDs and summaries
3. Status information
4. Any relevant patterns"""
                
                response = await ai_service.call_genai(
                    prompt=analysis_prompt,
                    temperature=0.3,
                    max_tokens=2000
                )
            else:
                response = result
            
            return {
                "success": True,
                "prompt": user_prompt,
                "intent": action.value,
                "response": response,
                "tickets": context.last_search_results
            }
        
        elif action == ActionType.CREATE:
            # Extract ticket details using AI
            extract_prompt = f"""Extract ticket details from this request:
"{user_prompt}"

Return a JSON object with:
- summary: brief ticket title
- description: detailed description
- issue_type: Story, Bug, or Task
- priority: Low, Medium, High, or Critical

JSON only, no other text:"""
            
            extracted = await ai_service.call_genai(
                prompt=extract_prompt,
                temperature=0.1,
                max_tokens=500
            )
            
            try:
                json_match = re.search(r'\{[^}]+\}', extracted, re.DOTALL)
                ticket_data = json.loads(json_match.group()) if json_match else json.loads(extracted)
                
                result = await create_ticket_tool(jira_service, json.dumps(ticket_data))
                
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
            # Extract update details using AI
            extract_prompt = f"""Extract update details from this request for ticket {ticket_key}:
"{user_prompt}"

Return a JSON object with any of these fields to update:
- status: new status (To Do, In Progress, Done, etc.)
- priority: new priority
- comment: comment to add

JSON only, no other text:"""
            
            extracted = await ai_service.call_genai(
                prompt=extract_prompt,
                temperature=0.1,
                max_tokens=500
            )
            
            try:
                json_match = re.search(r'\{[^}]+\}', extracted, re.DOTALL)
                update_data = json.loads(json_match.group()) if json_match else json.loads(extracted)
                update_data['ticket_key'] = ticket_key
                
                result = await update_ticket_tool(jira_service, json.dumps(update_data))
                
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
            result = await get_details_tool(jira_service, ticket_key)
            return {
                "success": True,
                "prompt": user_prompt,
                "intent": action.value,
                "response": result,
                "tickets": []
            }
        
        else:
            # Default search
            result = await search_tickets_tool(jira_service, context, user_prompt)
            return {
                "success": True,
                "prompt": user_prompt,
                "intent": "search",
                "response": result,
                "tickets": context.last_search_results
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
