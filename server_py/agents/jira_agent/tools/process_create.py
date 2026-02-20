"""Process create ticket requests with validation and contextual awareness."""
import json
import re
from typing import Dict, Any, Optional

from core.logging import log_error, log_info
from prompts import prompt_loader
from .ticket_tools import TicketToolsContext, create_ticket_tool
from .enrich_context import enrich_with_context
from ..conversation_manager import ConversationContext, ConversationState
from ..helpers import validate_create_ticket_data, generate_info_request_message


async def process_create_ticket(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process create ticket request with validation and contextual awareness."""
    enriched_context = {}
    summary = conversation_ctx.collected_data.get('summary') or user_prompt
    has_description = bool(conversation_ctx.collected_data.get('description'))

    if context and not has_description:
        log_info(f"Searching KB for: {summary}", "direct_processor")
        enriched_context = await enrich_with_context(summary, jira_service, ai_service, context)

    conversation_history = "\n".join([
        f"{msg['role']}: {msg['content']}"
        for msg in conversation_ctx.messages[-5:]
    ])

    if len(conversation_ctx.messages) >= 2:
        context_info = ""
        if enriched_context.get("has_context"):
            context_parts = []
            if enriched_context.get("knowledge_context"):
                context_parts.append(f"Reference info: {enriched_context['knowledge_context']}")
            if enriched_context.get("jira_context"):
                context_parts.append(f"Similar tickets: {enriched_context['jira_context']}")

            if context_parts:
                context_info = "\n".join(context_parts)
                context_info = f"\n\nContext: {context_info}"

        extract_prompt = prompt_loader.get_prompt("direct_processor.yml", "extract_conversation_ticket_data").format(
            conversation_history=conversation_history,
            user_prompt=user_prompt,
            collected_data=json.dumps(conversation_ctx.collected_data),
            context_info=context_info
        )

        try:
            extracted = await ai_service.call_genai(
                prompt=extract_prompt,
                temperature=0.1,
                max_tokens=500
            )

            json_match = re.search(r'\{[^}]*\}', extracted, re.DOTALL)
            ai_data = json.loads(json_match.group()) if json_match else json.loads(extracted)

            for key, value in ai_data.items():
                if value and str(value).strip():
                    conversation_ctx.collected_data[key] = value

        except Exception as e:
            log_error(f"AI extraction error: {e}", "direct_processor")

    context_hints = {}
    if enriched_context.get('has_context'):
        context_hints['has_context'] = True
        if enriched_context.get('jira_context'):
            context_hints['similar_tickets'] = enriched_context.get('jira_context', '').count('**')
        if enriched_context.get('knowledge_context'):
            context_hints['kb_suggestions'] = True

    if enriched_context.get('knowledge_context') and conversation_ctx.collected_data.get('summary') and not has_description:
        log_info("Auto-generating detailed description from knowledge base", "direct_processor")
        try:
            kb_content = enriched_context.get('knowledge_context', '')
            summary_text = conversation_ctx.collected_data.get('summary', '')
            issue_type = conversation_ctx.collected_data.get('issue_type', 'Story')

            enhance_prompt = prompt_loader.get_prompt("direct_processor.yml", "enhance_description").format(
                issue_type=issue_type,
                summary_text=summary_text,
                kb_content=kb_content
            )

            enhanced_description = await ai_service.call_genai(
                prompt=enhance_prompt,
                temperature=0.3,
                max_tokens=1500
            )

            if enhanced_description and len(enhanced_description) > 50:
                conversation_ctx.collected_data['description'] = enhanced_description.strip()
                log_info("Generated detailed description from KB content", "direct_processor")
        except Exception as e:
            log_error(f"Failed to generate description from KB: {e}", "direct_processor")

    is_complete, missing_fields = validate_create_ticket_data(user_prompt, conversation_ctx.collected_data, context_hints)

    if not is_complete:
        if enriched_context.get('knowledge_context'):
            missing_fields = [f for f in missing_fields if f.field != 'description']
            is_complete = len(missing_fields) == 0

        if not is_complete:
            conversation_ctx.set_missing_fields(missing_fields)
            message = generate_info_request_message(missing_fields)

            return {
                "success": False,
                "state": conversation_ctx.state.value,
                "session_id": conversation_ctx.session_id,
                "prompt": user_prompt,
                "intent": "create",
                "response": message,
                "missing_fields": [f.to_dict() for f in missing_fields],
                "collected_data": conversation_ctx.collected_data,
                "tickets": []
            }

    conversation_ctx.state = ConversationState.PROCESSING
    result = await create_ticket_tool(jira_service, json.dumps(conversation_ctx.collected_data))
    conversation_ctx.state = ConversationState.COMPLETED

    return {
        "success": "\u2705" in result,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "create",
        "response": result,
        "collected_data": conversation_ctx.collected_data,
        "tickets": []
    }
