"""Direct processing fallback for JIRA agent with intelligent information gathering."""
import json
import re
from typing import Dict, Any, Optional, List

from core.logging import log_error, log_info
from core.database import get_db
from services.knowledge_base_service import KnowledgeBaseService
from .utils import ActionType
from .prompts import prompt_loader
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
        # Search knowledge base for relevant information
        db = get_db()
        kb_service = KnowledgeBaseService(db)
        
        # Extract keywords from user prompt for searching
        kb_results = kb_service.search_knowledge_base(
            project_id="global",
            query=user_prompt,
            limit=5  # Increased to 5 for better context
        )
        
        if kb_results:
            kb_contents = []
            for result in kb_results:
                content = result.get('content', '').strip()
                source = result.get('source', 'Unknown')
                if content and len(content) > 50:  # Only substantial content
                    # Include more content for detailed descriptions
                    kb_contents.append(f"[Source: {source}]\n{content[:800]}")
            
            if kb_contents:
                enriched_context["knowledge_context"] = "\n\n---\n\n".join(kb_contents)
                enriched_context["kb_results"] = kb_results  # Keep full results for description generation
                enriched_context["has_context"] = True
                log_info(f"📚 Found {len(kb_contents)} relevant KB documents", "context_enrichment")
        
        # Search for related Jira tickets
        try:
            jira_tickets = await jira_service.get_jira_stories()
            
            if jira_tickets:
                # Use AI to find most relevant tickets
                tickets_summary = "\n".join([
                    f"- {ticket['key']}: {ticket['summary']} ({ticket['status']}, {ticket['issueType']})"
                    for ticket in jira_tickets[:20]  # Limit to recent 20
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
                    # Find full details of relevant tickets
                    key_list = [k.strip() for k in relevant_keys.split(',')]
                    relevant_tickets = [
                        ticket for ticket in jira_tickets
                        if ticket['key'] in key_list
                    ]
                    
                    if relevant_tickets:
                        jira_details = []
                        for ticket in relevant_tickets[:3]:  # Max 3 tickets
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
    
    # Initialize conversation context if not provided
    if conversation_ctx is None:
        # Single-turn mode (backward compatible)
        return await _process_without_conversation(user_prompt, intent, jira_service, ai_service, context)
    
    # Multi-turn mode with conversation memory
    log_info(f"Processing with conversation memory. State: {conversation_ctx.state}, Messages: {len(conversation_ctx.messages)}", "direct_processor")
    
    try:
        # Handle continuation of awaiting info state
        if conversation_ctx.state == ConversationState.AWAITING_INFO:
            return await _handle_info_response(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        # Extract initial data from prompt
        extracted_data = extract_ticket_data_from_prompt(user_prompt)
        conversation_ctx.update_collected_data(extracted_data)
        conversation_ctx.action_type = action.value
        conversation_ctx.original_intent = user_prompt
        
        log_info(f"Extracted data: {extracted_data}", "direct_processor")
        
        # Route based on action type
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
            # Default search
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


async def _process_create_ticket(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process create ticket request with validation and contextual awareness."""
    # Enrich with knowledge base and Jira context
    # Search KB when we have a summary but no description yet
    enriched_context = {}
    summary = conversation_ctx.collected_data.get('summary') or user_prompt
    has_description = bool(conversation_ctx.collected_data.get('description'))
    
    if context and not has_description:
        log_info(f"🔍 Searching KB for: {summary}", "direct_processor")
        enriched_context = await _enrich_with_context(summary, jira_service, ai_service, context)
    
    # Build context from conversation history
    conversation_history = "\n".join([
        f"{msg['role']}: {msg['content']}" 
        for msg in conversation_ctx.messages[-5:]  # Last 5 messages for context
    ])
    
    # Only use AI extraction if we have substantial conversation history
    # Otherwise, let the interactive process gather info step by step
    if len(conversation_ctx.messages) >= 2:
        # Build context-aware extraction prompt with conversation memory
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
        
        # Use AI to extract ticket details with full conversation context and memory
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
            
            # Only update with non-empty values
            for key, value in ai_data.items():
                if value and str(value).strip():
                    conversation_ctx.collected_data[key] = value
            
        except Exception as e:
            log_error(f"AI extraction error: {e}", "direct_processor")
    
    # Validate if we have all required info
    # Prepare context hints for validation
    context_hints = {}
    if enriched_context.get('has_context'):
        context_hints['has_context'] = True
        if enriched_context.get('jira_context'):
            # Count related tickets
            context_hints['similar_tickets'] = enriched_context.get('jira_context', '').count('**')
        if enriched_context.get('knowledge_context'):
            context_hints['kb_suggestions'] = True
    
    # If we have KB content and a summary, auto-generate description from KB
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
        # Filter out description from missing fields if we have KB content (will be auto-generated)
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
    
    # All info collected, create the ticket
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
    
    # Extract parent key from prompt or collected data
    parent_key = conversation_ctx.collected_data.get('parent_key')
    if not parent_key:
        # Try to extract from prompt
        ticket_match = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
        if ticket_match:
            parent_key = ticket_match.group(1)
            conversation_ctx.collected_data['parent_key'] = parent_key
    
    # Check if we have all required information
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
    
    # Create the subtask
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
    
    # Try to extract ticket keys from the prompt
    ticket_keys = re.findall(r'\b([A-Z]{2,10}-\d+)\b', user_prompt)
    
    source_key = conversation_ctx.collected_data.get('source_key')
    target_key = conversation_ctx.collected_data.get('target_key')
    
    # If we found multiple keys in the prompt, use them
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
    
    # Check for link type
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
    
    # Create the link
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
    log_info(f"🔎 Processing issue report: {user_prompt}", "direct_processor")
    
    # Check if we're waiting for user's action choice
    pending_action = conversation_ctx.collected_data.get('pending_action_choice')
    if pending_action:
        # User is responding to "what do you want to do?"
        response_lower = user_prompt.lower()
        
        # Handle simple yes/no confirmations
        if any(word in response_lower for word in ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'please', 'go ahead']):
            # Affirmative response - create the ticket
            conversation_ctx.collected_data['summary'] = conversation_ctx.collected_data.get('issue_description', user_prompt)
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            return await _process_create_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif any(word in response_lower for word in ['no', 'nope', 'cancel', 'nevermind', 'never mind']):
            # User doesn't want to proceed
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
            # User wants to create a new ticket
            conversation_ctx.collected_data['summary'] = conversation_ctx.collected_data.get('issue_description', user_prompt)
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            return await _process_create_ticket(user_prompt, conversation_ctx, jira_service, ai_service, context)
        
        elif any(word in response_lower for word in ['update', 'add', 'comment']):
            # User wants to update existing ticket - need to know which one
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
            # User wants to view details of a ticket
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
                # Ask for ticket key
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
            # User provided a ticket key - check if they said "view" or default to details
            ticket_key = re.search(r'\b([A-Z]{2,10}-\d+)\b', user_prompt).group(1)
            conversation_ctx.collected_data['ticket_key'] = ticket_key
            conversation_ctx.collected_data.pop('pending_action_choice', None)
            # Default to showing details when they just provide a ticket key
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
    
    # First time processing - extract issue description and search
    # Use AI to extract what the issue is about
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
    
    # Store the issue description for later
    conversation_ctx.collected_data['issue_description'] = issue_summary
    conversation_ctx.collected_data['original_report'] = user_prompt
    
    # Search for related tickets
    log_info(f"🔍 Searching for related tickets: {search_query}", "direct_processor")
    search_result = await search_tickets_tool(jira_service, context, search_query, ai_service)
    
    # Check if we found any related tickets
    related_tickets = context.last_search_results if context else []
    
    if related_tickets:
        # Found related tickets - show them and ask what to do
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
        # No related tickets found - offer to create
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


async def _process_update_ticket(
    user_prompt: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: Optional[TicketToolsContext] = None
) -> Dict[str, Any]:
    """Process update ticket request with validation and contextual awareness."""
    # Build context from conversation history
    conversation_history = "\n".join([
        f"{msg['role']}: {msg['content']}" 
        for msg in conversation_ctx.messages[-5:]  # Last 5 messages for context
    ])
    
    # Enrich with current ticket details if we have a ticket key
    ticket_context = ""
    ticket_key = conversation_ctx.collected_data.get('ticket_key')
    if ticket_key:
        log_info(f"🔍 Fetching current details for ticket {ticket_key}", "direct_processor")
        try:
            ticket_details = await get_details_tool(jira_service, ticket_key)
            ticket_context = f"\n\n**CURRENT TICKET DETAILS:**\n{ticket_details}\n"
        except Exception as e:
            log_error(f"Error fetching ticket details: {e}", "direct_processor")
    
    # Use AI to extract update details with full conversation context
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
    
    # Validate if we have all required info
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
    
    # All info collected, update the ticket
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
    # Enrich with knowledge base context for search
    log_info("🔍 Enriching search with KB and Jira context", "direct_processor")
    enriched_context = await _enrich_with_context(user_prompt, jira_service, ai_service, context)
    
    # Check if user is referencing previous searches in conversation
    conversation_history = conversation_ctx.get_conversation_history(5)
    has_previous_context = len(conversation_ctx.messages) > 2
    
    # Validate query specificity
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
    
    # Perform search
    conversation_ctx.state = ConversationState.PROCESSING
    result = await search_tickets_tool(jira_service, context, user_prompt, ai_service)
    
    # Generate AI analysis of results with enriched context
    if context.last_search_results:
        tickets_summary = format_tickets_for_agent(context.last_search_results)
        
        # Build context-aware response
        context_info = ""
        if enriched_context.get("has_context"):
            context_parts = []
            if enriched_context.get("jira_context"):
                context_parts.append(f"Related: {enriched_context['jira_context']}")
            
            if context_parts:
                context_info = f"\n\n{context_parts[0]}"
        
        # Include conversation history if available
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


async def _handle_info_response(
    user_response: str,
    conversation_ctx: ConversationContext,
    jira_service,
    ai_service,
    context: TicketToolsContext
) -> Dict[str, Any]:
    """Handle user's response to information request."""
    log_info(f"Handling info response. Missing fields: {len(conversation_ctx.missing_fields)}", "direct_processor")
    
    # Check if user wants to cancel
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
    
    # Merge user response into collected data
    if conversation_ctx.missing_fields:
        # Take the first missing field and try to extract answer
        current_field = conversation_ctx.missing_fields[0]
        conversation_ctx.collected_data = merge_user_response(
            conversation_ctx.collected_data,
            user_response,
            current_field
        )
        
        # Remove the field we just collected
        conversation_ctx.missing_fields.pop(0)
    
    # Check if there are still missing fields
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
    
    # All info collected, now process the original intent
    conversation_ctx.clear_missing_fields()
    
    # Route based on original action type
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
        # Default to search
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
