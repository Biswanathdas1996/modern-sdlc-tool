"""Issue report processing, info response handling, and legacy single-turn processing."""
import json
import re
from typing import Dict, Any, Optional

from core.logging import log_error, log_info
from prompts import prompt_loader
from .utils import ActionType
from .tools import (
    TicketToolsContext,
    search_tickets_tool,
    create_ticket_tool,
    update_ticket_tool,
    get_details_tool,
    format_tickets_for_agent,
)
from .conversation_manager import ConversationContext, ConversationState
from .info_gathering import (
    merge_user_response,
    generate_info_request_message
)


async def _process_issue_report(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process issue report - search for related tickets first, then ask what to do.
    
    This provides a smarter flow when users describe problems:
    1. Extract the issue description
    2. Search for related existing tickets
    3. Present findings and ask what action to take
    """
    from .ticket_actions import _process_create_ticket, _process_update_ticket

    log_info(f"🔎 Processing issue report: {user_prompt}", "direct_processor")
    
    pending_action = conversation_ctx.collected_data.get('pending_action_choice')
    if pending_action:
        response_lower = user_prompt.lower()
        
        if any(word in response_lower for word in ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'please', 'go ahead']):
            conversation_ctx.collected_data['summary'] = conversation_ctx.collected_data.get('issue_description', user_prompt)
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            return await _process_create_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif any(word in response_lower for word in ['no', 'nope', 'cancel', 'nevermind', 'never mind']):
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            conversation_ctx.state = ConversationState.COMPLETED
            return {
                "success": True,
                "state": conversation_ctx.state.value,
                "session_id": conversation_ctx.session_id,
                "prompt": user_prompt,
                "intent": "issue_report",
                "response": "No problem! Let me know if there's anything else I can help you with.",
                "collected_data": {},
                "tickets": []
            }
        
        elif any(word in response_lower for word in ['create', 'new', 'open', 'file', 'raise']):
            conversation_ctx.collected_data['summary'] = conversation_ctx.collected_data.get('issue_description', user_prompt)
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            return await _process_create_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif any(word in response_lower for word in ['update', 'add', 'comment']):
            if not conversation_ctx.collected_data.get('ticket_key'):
                conversation_ctx.state = ConversationState.AWAITING_INFO
                return {
                    "success": False,
                    "state": conversation_ctx.state.value,
                    "session_id": conversation_ctx.session_id,
                    "prompt": user_prompt,
                    "intent": "issue_report",
                    "response": "Which ticket would you like to update? Please provide the ticket key (e.g., PROJ-123) from the list above.",
                    "missing_fields": [{"field": "ticket_key", "description": "Ticket to update"}],
                    "collected_data": conversation_ctx.collected_data,
                    "tickets": context.last_search_results if context else []
                }
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            return await _process_update_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif any(word in response_lower for word in ['view', 'details', 'show', 'see']):
            ticket_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
            if ticket_match:
                ticket_key = ticket_match.group(1)
                conversation_ctx.collected_data.pop('pending_action_choice', None)
                conversation_ctx.state = ConversationState.COMPLETED
                result = await get_details_tool(jira_service, ticket_key)
                return {
                    "success": True,
                    "state": conversation_ctx.state.value,
                    "session_id": conversation_ctx.session_id,
                    "prompt": user_prompt,
                    "intent": "get_details",
                    "response": result,
                    "collected_data": conversation_ctx.collected_data,
                    "tickets": []
                }
            else:
                conversation_ctx.state = ConversationState.AWAITING_INFO
                return {
                    "success": False,
                    "state": conversation_ctx.state.value,
                    "session_id": conversation_ctx.session_id,
                    "prompt": user_prompt,
                    "intent": "issue_report",
                    "response": "Which ticket would you like to view? Please provide the ticket key (e.g., PROJ-123).",
                    "missing_fields": [{"field": "ticket_key", "description": "Ticket to view"}],
                    "collected_data": conversation_ctx.collected_data,
                    "tickets": context.last_search_results if context else []
                }
        
        elif re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt):
            ticket_key = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt).group(1)
            conversation_ctx.collected_data['ticket_key'] = ticket_key
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            conversation_ctx.state = ConversationState.COMPLETED
            result = await get_details_tool(jira_service, ticket_key)
            return {
                "success": True,
                "state": conversation_ctx.state.value,
                "session_id": conversation_ctx.session_id,
                "prompt": user_prompt,
                "intent": "get_details",
                "response": result,
                "collected_data": conversation_ctx.collected_data,
                "tickets": []
            }
    
    extract_prompt = prompt_loader.get_prompt("direct_processor.yml", "extract_search_query").format(
        user_prompt=user_prompt
    )

    try:
        extracted = await ai_service.call_genai(
            prompt=extract_prompt,
            temperature=0.1,
            max_tokens=200
        )
        
        json_match = re.search(r'\{[^}]*\}', extracted, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            search_query = data.get('search_query', user_prompt)
            issue_summary = data.get('issue_summary', user_prompt)
        else:
            search_query = user_prompt
            issue_summary = user_prompt
    except Exception as e:
        log_error(f"Issue extraction failed: {e}", "direct_processor")
        search_query = user_prompt
        issue_summary = user_prompt
    
    conversation_ctx.collected_data['issue_description'] = issue_summary
    conversation_ctx.collected_data['original_report'] = user_prompt
    
    log_info(f"🔍 Searching for related tickets: {search_query}", "direct_processor")
    search_result = await search_tickets_tool(jira_service, context, search_query, ai_service)
    
    related_tickets = context.last_search_results if context else []
    
    if related_tickets:
        conversation_ctx.collected_data['pending_action_choice'] = True
        conversation_ctx.state = ConversationState.AWAITING_INFO
        
        tickets_list = "\n".join([
            f"- **{t.get('key')}**: {t.get('summary')} ({t.get('status')})"
            for t in related_tickets[:5]
        ])
        
        response = f"""I found **{len(related_tickets)}** related ticket(s) that might be relevant:

{tickets_list}

**What would you like to do?**
1. **Create a new ticket** for this issue
2. **Update an existing ticket** from the list above (add a comment or change status)
3. **View details** of a specific ticket (just tell me the ticket key)

Please let me know how you'd like to proceed."""

        return {
            "success": True,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "issue_report",
            "response": response,
            "collected_data": conversation_ctx.collected_data,
            "tickets": related_tickets[:5],
            "action_choices": ["create_new", "update_existing", "view_details"]
        }
    else:
        conversation_ctx.collected_data['pending_action_choice'] = True
        conversation_ctx.state = ConversationState.AWAITING_INFO
        
        response = f"""I searched for related tickets but didn't find any existing issues matching your description.

**Issue detected:** {issue_summary}

Would you like me to **create a new ticket** for this issue?"""

        return {
            "success": True,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "issue_report",
            "response": response,
            "collected_data": conversation_ctx.collected_data,
            "tickets": [],
            "action_choices": ["create_new"]
        }


async def _handle_info_response(
    user_response: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: TicketToolsContext
) -> Dict[str, Any]:
    """Handle user's response to information request."""
    from .ticket_actions import (
        _process_create_ticket,
        _process_create_subtask,
        _process_link_issues,
        _process_update_ticket,
        _process_search_tickets,
    )

    log_info(f"Handling info response. Missing fields: {len(conversation_ctx.missing_fields)}", "direct_processor")
    
    cancel_phrases = ["cancel", "stop", "abort", "quit", "exit", "nevermind", "never mind"]
    if any(phrase in user_response.lower() for phrase in cancel_phrases):
        conversation_ctx.state = ConversationState.COMPLETED
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_response,
            "intent": conversation_ctx.action_type,
            "response": "👍 Got it! Operation cancelled. Is there anything else I can help you with?",
            "tickets": []
        }
    
    if conversation_ctx.missing_fields:
        current_field = conversation_ctx.missing_fields[0]
        conversation_ctx.collected_data = merge_user_response(
            conversation_ctx.collected_data,
            user_response,
            current_field
        )
        
        conversation_ctx.missing_fields.pop(0)
    
    if conversation_ctx.missing_fields:
        message = generate_info_request_message(conversation_ctx.missing_fields)
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_response,
            "intent": conversation_ctx.action_type,
            "response": message,
            "missing_fields": [f.to_dict() for f in conversation_ctx.missing_fields],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }
    
    conversation_ctx.clear_missing_fields()
    
    if conversation_ctx.action_type == ActionType.CREATE.value:
        return await _process_create_ticket(conversation_ctx.original_intent, conversation_ctx, jira_service, ai_service, context)
    elif conversation_ctx.action_type == ActionType.UPDATE.value:
        return await _process_update_ticket(conversation_ctx.original_intent, conversation_ctx, jira_service, ai_service, context)
    elif conversation_ctx.action_type == ActionType.SEARCH.value:
        return await _process_search_tickets(conversation_ctx.original_intent, conversation_ctx, jira_service, ai_service, context)
    elif conversation_ctx.action_type == ActionType.SUBTASK.value:
        return await _process_create_subtask(conversation_ctx.original_intent, conversation_ctx, jira_service, ai_service, context)
    elif conversation_ctx.action_type == ActionType.LINK.value:
        return await _process_link_issues(conversation_ctx.original_intent, conversation_ctx, jira_service, ai_service, context)
    elif conversation_ctx.action_type == ActionType.ISSUE_REPORT.value:
        return await _process_issue_report(user_response, conversation_ctx, jira_service, ai_service, context)
    else:
        return await _process_search_tickets(conversation_ctx.original_intent, conversation_ctx, jira_service, ai_service, context)


async def _process_without_conversation(
    user_prompt: str,
    intent: Dict[str, Any],
    jira_service,
    ai_service,
    context: TicketToolsContext
) -> Dict[str, Any]:
    """Legacy single-turn processing without conversation context."""
    action = intent.get('action', ActionType.UNKNOWN)
    ticket_key = intent.get('ticket_key')
    
    try:
        if action == ActionType.SEARCH or action == ActionType.UNKNOWN:
            result = await search_tickets_tool(jira_service, context, user_prompt, ai_service)
            
            if context.last_search_results:
                tickets_summary = format_tickets_for_agent(context.last_search_results)
                analysis_prompt = prompt_loader.get_prompt("direct_processor.yml", "search_analysis").format(
                    user_prompt=user_prompt,
                    tickets_summary=tickets_summary
                )
                
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
            extract_prompt = prompt_loader.get_prompt("direct_processor.yml", "extract_simple_ticket_data").format(
                user_prompt=user_prompt
            )
            
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
            extract_prompt = prompt_loader.get_prompt("direct_processor.yml", "extract_simple_update_details").format(
                ticket_key=ticket_key,
                user_prompt=user_prompt
            )
            
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
            result = await search_tickets_tool(jira_service, context, user_prompt, ai_service)
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
