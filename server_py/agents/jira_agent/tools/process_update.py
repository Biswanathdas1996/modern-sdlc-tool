"""Process update ticket requests with validation and contextual awareness."""
import json
import re
from typing import Dict, Any, Optional

from core.logging import log_error, log_info
from prompts import prompt_loader
from .ticket_tools import TicketToolsContext, update_ticket_tool, get_details_tool
from ..conversation_manager import ConversationContext, ConversationState
from ..helpers import validate_update_ticket_data, generate_info_request_message


async def process_update_ticket(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process update ticket request with validation and contextual awareness."""
    conversation_history = "\n".join([
        f"{msg['role']}: {msg['content']}"
        for msg in conversation_ctx.messages[-5:]
    ])

    ticket_context = ""
    ticket_key = conversation_ctx.collected_data.get('ticket_key')
    if ticket_key:
        log_info(f"Fetching current details for ticket {ticket_key}", "direct_processor")
        try:
            ticket_details = await get_details_tool(jira_service, ticket_key)
            ticket_context = f"\n\n**CURRENT TICKET DETAILS:**\n{ticket_details}\n"
        except Exception as e:
            log_error(f"Error fetching ticket details: {e}", "direct_processor")

    extract_prompt = prompt_loader.get_prompt("direct_processor.yml", "extract_update_details").format(
        conversation_history=conversation_history,
        user_prompt=user_prompt,
        collected_data=json.dumps(conversation_ctx.collected_data),
        ticket_context=ticket_context
    )

    try:
        extracted = await ai_service.call_genai(
            prompt=extract_prompt,
            temperature=0.1,
            max_tokens=500
        )

        json_match = re.search(r'\{[^}]+\}', extracted, re.DOTALL)
        ai_data = json.loads(json_match.group()) if json_match else json.loads(extracted)
        conversation_ctx.update_collected_data(ai_data)

    except Exception as e:
        log_error(f"AI extraction error: {e}", "direct_processor")

    is_complete, missing_fields = validate_update_ticket_data(user_prompt, conversation_ctx.collected_data)

    if not is_complete:
        conversation_ctx.set_missing_fields(missing_fields)
        message = generate_info_request_message(missing_fields)

        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "update",
            "response": message,
            "missing_fields": [f.to_dict() for f in missing_fields],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }

    conversation_ctx.state = ConversationState.PROCESSING
    result = await update_ticket_tool(jira_service, json.dumps(conversation_ctx.collected_data))
    conversation_ctx.state = ConversationState.COMPLETED

    return {
        "success": "\u2705" in result,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "update",
        "response": result,
        "collected_data": conversation_ctx.collected_data,
        "tickets": []
    }
