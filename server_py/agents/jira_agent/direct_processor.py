"""Direct processing dispatcher for JIRA agent with intelligent routing."""
from typing import Dict, Any, Optional

from core.logging import log_error, log_info
from .utils import ActionType
from .tools import (
    TicketToolsContext,
    get_details_tool,
    enrich_with_context,
    process_create_ticket,
    process_update_ticket,
    process_search_tickets,
    process_create_subtask,
    process_link_issues,
    process_issue_report,
    handle_info_response,
    process_without_conversation,
)
from .conversation_manager import ConversationContext, ConversationState
from .helpers import extract_ticket_data_from_prompt

_enrich_with_context = enrich_with_context


async def direct_process(
    user_prompt: str,
    intent: Dict[str, Any],
    jira_service,
    ai_service,
    context: TicketToolsContext,
    conversation_ctx: Optional[ConversationContext] = None
) -> Dict[str, Any]:
    """Direct processing with intelligent information gathering and conversation memory."""
    action = intent.get('action', ActionType.UNKNOWN)
    ticket_key = intent.get('ticket_key')

    if conversation_ctx is None:
        return await process_without_conversation(user_prompt, intent, jira_service, ai_service, context)

    log_info(f"Processing with conversation memory. State: {conversation_ctx.state}, Messages: {len(conversation_ctx.messages)}", "direct_processor")

    try:
        if conversation_ctx.state == ConversationState.AWAITING_INFO:
            return await handle_info_response(user_prompt, conversation_ctx, jira_service, ai_service, context)

        extracted_data = extract_ticket_data_from_prompt(user_prompt)
        conversation_ctx.update_collected_data(extracted_data)
        conversation_ctx.action_type = action.value
        conversation_ctx.original_intent = user_prompt

        log_info(f"Extracted data: {extracted_data}", "direct_processor")

        if action == ActionType.CREATE:
            return await process_create_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)

        elif action == ActionType.UPDATE:
            return await process_update_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)

        elif action == ActionType.SEARCH or action == ActionType.UNKNOWN:
            return await process_search_tickets(user_prompt, conversation_ctx, jira_service, ai_service, context)

        elif action == ActionType.GET_DETAILS and ticket_key:
            result = await get_details_tool(jira_service, ticket_key)
            conversation_ctx.state = ConversationState.COMPLETED
            return {
                "success": True,
                "state": conversation_ctx.state.value,
                "session_id": conversation_ctx.session_id,
                "prompt": user_prompt,
                "intent": action.value,
                "response": result,
                "tickets": [],
                "collected_data": conversation_ctx.collected_data
            }

        elif action == ActionType.SUBTASK:
            return await process_create_subtask(user_prompt, conversation_ctx, jira_service, ai_service, context)

        elif action == ActionType.LINK:
            return await process_link_issues(user_prompt, conversation_ctx, jira_service, ai_service, context)

        elif action == ActionType.ISSUE_REPORT:
            return await process_issue_report(user_prompt, conversation_ctx, jira_service, ai_service, context)

        else:
            return await process_search_tickets(user_prompt, conversation_ctx, jira_service, ai_service, context)

    except Exception as e:
        log_error(f"Direct processing error: {e}", "direct_processor", e)
        return {
            "success": False,
            "state": ConversationState.INITIAL.value,
            "session_id": conversation_ctx.session_id if conversation_ctx else "unknown",
            "prompt": user_prompt,
            "intent": action.value,
            "response": f"Error: {str(e)}",
            "tickets": []
        }
