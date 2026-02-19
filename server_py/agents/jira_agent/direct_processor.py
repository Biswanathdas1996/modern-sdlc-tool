"""Direct processing fallback for JIRA agent with intelligent information gathering."""
import json
import re
from typing import Dict, Any, Optional, List

from core.logging import log_error, log_info
from core.database import get_db
from services.knowledge_base_service import KnowledgeBaseService
from .utils import ActionType
from prompts import prompt_loader
from .tools import (
    TicketToolsContext,
    search_tickets_tool,
    create_ticket_tool,
    update_ticket_tool,
    get_details_tool,
    format_tickets_for_agent,
    create_subtask_tool,
    link_issues_tool
)
from .conversation_manager import ConversationContext, ConversationState
from .info_gathering import (
    validate_create_ticket_data,
    validate_update_ticket_data,
    validate_search_query,
    extract_ticket_data_from_prompt,
    merge_user_response,
    generate_info_request_message
)
from .ticket_actions import (
    _process_create_ticket,
    _process_create_subtask,
    _process_link_issues,
    _process_update_ticket,
    _process_search_tickets,
)
from .issue_actions import (
    _process_issue_report,
    _handle_info_response,
    _process_without_conversation,
)


async def _enrich_with_context(
    user_prompt: str,
    jira_service,
    ai_service,
    context: TicketToolsContext
) -> Dict[str, Any]:
    """
    Enrich the agent's understanding with knowledge base and existing Jira tickets.
    
    Returns:
        Dictionary with knowledge_context and jira_context
    """
    enriched_context = {
        "knowledge_context": "",
        "jira_context": "",
        "has_context": False
    }
    
    try:
        db = get_db()
        kb_service = KnowledgeBaseService(db)
        
        kb_results = kb_service.search_knowledge_base(
            project_id="global",
            query=user_prompt,
            limit=5
        )
        
        if kb_results:
            kb_contents = []
            for result in kb_results:
                content = result.get('content', '').strip()
                source = result.get('source', 'Unknown')
                if content and len(content) > 50:
                    kb_contents.append(f"[Source: {source}]\n{content[:800]}")
            
            if kb_contents:
                enriched_context["knowledge_context"] = "\n\n---\n\n".join(kb_contents)
                enriched_context["kb_results"] = kb_results
                enriched_context["has_context"] = True
                log_info(f"📚 Found {len(kb_contents)} relevant KB documents", "context_enrichment")
        
        try:
            jira_tickets = await jira_service.get_jira_stories()
            
            if jira_tickets:
                tickets_summary = "\n".join([
                    f"- {ticket['key']}: {ticket['summary']} ({ticket['status']}, {ticket['issueType']})"
                    for ticket in jira_tickets[:20]
                ])
                
                relevance_prompt = prompt_loader.get_prompt("direct_processor.yml", "relevance_check").format(
                    user_prompt=user_prompt,
                    tickets_summary=tickets_summary
                )
                
                relevant_keys = await ai_service.call_genai(
                    prompt=relevance_prompt,
                    temperature=0.1,
                    max_tokens=100
                )
                
                relevant_keys = relevant_keys.strip()
                
                if relevant_keys and relevant_keys != "NONE":
                    key_list = [k.strip() for k in relevant_keys.split(',')]
                    relevant_tickets = [
                        ticket for ticket in jira_tickets
                        if ticket['key'] in key_list
                    ]
                    
                    if relevant_tickets:
                        jira_details = []
                        for ticket in relevant_tickets[:3]:
                            jira_details.append(
                                f"{ticket['key']}: {ticket['summary']} [{ticket['status']}]"
                            )
                        
                        enriched_context["jira_context"] = "\n".join(jira_details)
                        enriched_context["has_context"] = True
                        log_info(f"🎫 Found {len(jira_details)} relevant JIRA tickets", "context_enrichment")
        
        except Exception as e:
            log_error(f"Error fetching Jira context: {e}", "context_enrichment")
    
    except Exception as e:
        log_error(f"Error enriching context: {e}", "context_enrichment")
    
    return enriched_context


async def direct_process(
    user_prompt: str,
    intent: Dict[str, Any],
    jira_service,
    ai_service,
    context: TicketToolsContext,
    conversation_ctx: Optional[ConversationContext] = None
) -> Dict[str, Any]:
    """
    Direct processing with intelligent information gathering and conversation memory.
    Asks user for missing information before proceeding while maintaining full session context.
    
    Args:
        user_prompt: User's query
        intent: Analyzed intent with action type and ticket key
        jira_service: JiraService instance
        ai_service: AIService instance
        context: Shared context for storing state
        conversation_ctx: Conversation context for multi-turn interactions with memory
        
    Returns:
        Response dictionary with success status, results, and conversation context
    """
    action = intent.get('action', ActionType.UNKNOWN)
    ticket_key = intent.get('ticket_key')
    
    if conversation_ctx is None:
        return await _process_without_conversation(user_prompt, intent, jira_service, ai_service, context)
    
    log_info(f"Processing with conversation memory. State: {conversation_ctx.state}, Messages: {len(conversation_ctx.messages)}", "direct_processor")
    
    try:
        if conversation_ctx.state == ConversationState.AWAITING_INFO:
            return await _handle_info_response(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        extracted_data = extract_ticket_data_from_prompt(user_prompt)
        conversation_ctx.update_collected_data(extracted_data)
        conversation_ctx.action_type = action.value
        conversation_ctx.original_intent = user_prompt
        
        log_info(f"Extracted data: {extracted_data}", "direct_processor")
        
        if action == ActionType.CREATE:
            return await _process_create_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif action == ActionType.UPDATE:
            return await _process_update_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif action == ActionType.SEARCH or action == ActionType.UNKNOWN:
            return await _process_search_tickets(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
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
            return await _process_create_subtask(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif action == ActionType.LINK:
            return await _process_link_issues(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif action == ActionType.ISSUE_REPORT:
            return await _process_issue_report(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        else:
            return await _process_search_tickets(user_prompt, conversation_ctx, jira_service, ai_service, context)
            
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
