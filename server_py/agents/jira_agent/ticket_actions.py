"""Ticket action processors for JIRA agent - create, update, search, subtask, link operations."""
import json
import re
from typing import Dict, Any, Optional

from core.logging import log_error, log_info
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
    merge_user_response,
    generate_info_request_message
)


async def _process_create_ticket(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process create ticket request with validation and contextual awareness."""
    from .direct_processor import _enrich_with_context

    enriched_context = {}
    summary = conversation_ctx.collected_data.get('summary') or user_prompt
    has_description = bool(conversation_ctx.collected_data.get('description'))
    
    if context and not has_description:
        log_info(f"🔍 Searching KB for: {summary}", "direct_processor")
        enriched_context = await _enrich_with_context(summary, jira_service, ai_service, context)
    
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
        log_info("📝 Auto-generating detailed description from knowledge base", "direct_processor")
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
                log_info("✅ Generated detailed description from KB content", "direct_processor")
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
        "success": "✅" in result,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "create",
        "response": result,
        "collected_data": conversation_ctx.collected_data,
        "tickets": []
    }


async def _process_create_subtask(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process subtask creation request."""
    from .conversation_manager import InfoRequest
    
    parent_key = conversation_ctx.collected_data.get('parent_key')
    if not parent_key:
        ticket_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
        if ticket_match:
            parent_key = ticket_match.group(1)
            conversation_ctx.collected_data['parent_key'] = parent_key
    
    summary = conversation_ctx.collected_data.get('summary')
    description = conversation_ctx.collected_data.get('description', '')
    
    if not parent_key:
        missing = [InfoRequest(field="parent_key", description="Parent ticket key", required=True)]
        conversation_ctx.set_missing_fields(missing)
        conversation_ctx.state = ConversationState.AWAITING_INFO
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "subtask",
            "response": "I need to know which ticket to create the subtask under. Please provide the parent ticket key (e.g., PROJ-123).",
            "missing_fields": [f.to_dict() for f in missing],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }
    
    if not summary:
        missing = [InfoRequest(field="summary", description="Subtask summary", required=True)]
        conversation_ctx.set_missing_fields(missing)
        conversation_ctx.state = ConversationState.AWAITING_INFO
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "subtask",
            "response": f"What should the subtask under **{parent_key}** be about? Please provide a summary.",
            "missing_fields": [f.to_dict() for f in missing],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }
    
    log_info(f"📝 Creating subtask under {parent_key}: {summary}", "direct_processor")
    
    subtask_data = {
        "parent_key": parent_key,
        "summary": summary,
        "description": description,
        "priority": conversation_ctx.collected_data.get('priority', 'Medium')
    }
    
    conversation_ctx.state = ConversationState.PROCESSING
    result = await create_subtask_tool(jira_service, json.dumps(subtask_data))
    conversation_ctx.state = ConversationState.COMPLETED
    
    return {
        "success": "✅" in result,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "subtask",
        "response": result,
        "collected_data": conversation_ctx.collected_data,
        "tickets": []
    }


async def _process_link_issues(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process issue linking request."""
    from .conversation_manager import InfoRequest
    
    ticket_keys = re.findall(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
    
    source_key = conversation_ctx.collected_data.get('source_key')
    target_key = conversation_ctx.collected_data.get('target_key')
    
    if len(ticket_keys) >= 2 and not source_key and not target_key:
        source_key = ticket_keys[0]
        target_key = ticket_keys[1]
        conversation_ctx.collected_data['source_key'] = source_key
        conversation_ctx.collected_data['target_key'] = target_key
    elif len(ticket_keys) == 1:
        if not source_key:
            source_key = ticket_keys[0]
            conversation_ctx.collected_data['source_key'] = source_key
        elif not target_key:
            target_key = ticket_keys[0]
            conversation_ctx.collected_data['target_key'] = target_key
    
    link_type = conversation_ctx.collected_data.get('link_type', 'Relates')
    prompt_lower = user_prompt.lower()
    if 'block' in prompt_lower:
        link_type = 'Blocks'
    elif 'duplicate' in prompt_lower:
        link_type = 'Duplicate'
    elif 'relate' in prompt_lower:
        link_type = 'Relates'
    
    conversation_ctx.collected_data['link_type'] = link_type
    
    if not source_key:
        missing = [InfoRequest(field="source_key", description="Source ticket key", required=True)]
        conversation_ctx.set_missing_fields(missing)
        conversation_ctx.state = ConversationState.AWAITING_INFO
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "link",
            "response": "Which ticket would you like to link from? Please provide the source ticket key (e.g., PROJ-123).",
            "missing_fields": [f.to_dict() for f in missing],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }
    
    if not target_key:
        missing = [InfoRequest(field="target_key", description="Target ticket key", required=True)]
        conversation_ctx.set_missing_fields(missing)
        conversation_ctx.state = ConversationState.AWAITING_INFO
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "link",
            "response": f"Which ticket would you like to link **{source_key}** to? Please provide the target ticket key.",
            "missing_fields": [f.to_dict() for f in missing],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }
    
    log_info(f"🔗 Linking {source_key} to {target_key} ({link_type})", "direct_processor")
    
    link_data = {
        "source_key": source_key,
        "target_key": target_key,
        "link_type": link_type
    }
    
    conversation_ctx.state = ConversationState.PROCESSING
    result = await link_issues_tool(jira_service, json.dumps(link_data))
    conversation_ctx.state = ConversationState.COMPLETED
    
    return {
        "success": "✅" in result,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "link",
        "response": result,
        "collected_data": conversation_ctx.collected_data,
        "tickets": []
    }


async def _process_update_ticket(
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
        log_info(f"🔍 Fetching current details for ticket {ticket_key}", "direct_processor")
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
        "success": "✅" in result,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "update",
        "response": result,
        "collected_data": conversation_ctx.collected_data,
        "tickets": []
    }


async def _process_search_tickets(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: TicketToolsContext
) -> Dict[str, Any]:
    """Process search ticket request with contextual awareness and conversation memory."""
    from .direct_processor import _enrich_with_context

    log_info("🔍 Enriching search with KB and Jira context", "direct_processor")
    enriched_context = await _enrich_with_context(user_prompt, jira_service, ai_service, context)
    
    conversation_history = conversation_ctx.get_conversation_history(5)
    has_previous_context = len(conversation_ctx.messages) > 2
    
    is_complete, missing_fields = validate_search_query(user_prompt, conversation_ctx.collected_data)
    
    if not is_complete:
        conversation_ctx.set_missing_fields(missing_fields)
        message = generate_info_request_message(missing_fields)
        
        return {
            "success": False,
            "state": conversation_ctx.state.value,
            "session_id": conversation_ctx.session_id,
            "prompt": user_prompt,
            "intent": "search",
            "response": message,
            "missing_fields": [f.to_dict() for f in missing_fields],
            "collected_data": conversation_ctx.collected_data,
            "tickets": []
        }
    
    conversation_ctx.state = ConversationState.PROCESSING
    result = await search_tickets_tool(jira_service, context, user_prompt, ai_service)
    
    if context.last_search_results:
        tickets_summary = format_tickets_for_agent(context.last_search_results)
        
        context_info = ""
        if enriched_context.get("has_context"):
            context_parts = []
            if enriched_context.get("jira_context"):
                context_parts.append(f"Related: {enriched_context['jira_context']}")
            
            if context_parts:
                context_info = f"\n\n{context_parts[0]}"
        
        history_context = ""
        if has_previous_context:
            history_context = f"\n\nConversation History:\n{conversation_history}"
        
        analysis_prompt = prompt_loader.get_prompt("direct_processor.yml", "analyze_search_results").format(
            user_prompt=user_prompt,
            tickets_summary=tickets_summary,
            context_info=context_info,
            history_context=history_context,
            history_note='- Reference to previous conversation context if relevant' if has_previous_context else ''
        )
        
        response = await ai_service.call_genai(
            prompt=analysis_prompt,
            temperature=0.3,
            max_tokens=2000
        )
    else:
        response = result
    
    conversation_ctx.state = ConversationState.COMPLETED
    
    return {
        "success": True,
        "state": conversation_ctx.state.value,
        "session_id": conversation_ctx.session_id,
        "prompt": user_prompt,
        "intent": "search",
        "response": response,
        "tickets": context.last_search_results,
        "collected_data": conversation_ctx.collected_data
    }
