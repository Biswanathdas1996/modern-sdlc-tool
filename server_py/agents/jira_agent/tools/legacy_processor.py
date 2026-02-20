"""Legacy single-turn processing without conversation context."""
import json
import re
from typing import Dict, Any

from core.logging import log_error
from prompts import prompt_loader
from ..utils import ActionType
from .ticket_tools import (
    TicketToolsContext,
    search_tickets_tool,
    create_ticket_tool,
    update_ticket_tool,
    get_details_tool,
)
from .helpers import format_tickets_for_agent


async def process_without_conversation(
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
                    "success": "\u2705" in result,
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
                    "success": "\u2705" in result,
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
