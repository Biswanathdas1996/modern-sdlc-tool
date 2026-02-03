"""Direct processing fallback for JIRA agent with intelligent information gathering."""
import json
import re
from typing import Dict, Any, Optional, List

from core.logging import log_error, log_info
from core.database import get_db
from services.knowledge_base_service import KnowledgeBaseService
from .utils import ActionType
from .tools import (
    TicketToolsContext,
    search_tickets_tool,
    create_ticket_tool,
    update_ticket_tool,
    get_details_tool,
    format_tickets_for_agent
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
            limit=2  # Reduced to 2 most relevant
        )
        
        if kb_results:
            kb_contents = []
            for result in kb_results:
                content = result.get('content', '').strip()
                if content and len(content) > 50:  # Only substantial content
                    kb_contents.append(content[:300])  # Reduced to 300 chars
            
            if kb_contents:
                enriched_context["knowledge_context"] = "\n".join(kb_contents)
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
                
                relevance_prompt = f"""Given this user query: "{user_prompt}"

And these existing JIRA tickets:
{tickets_summary}

List the 3-5 most relevant ticket keys that relate to this query.
Respond with ONLY ticket keys separated by commas (e.g., PROJ-123, PROJ-456).
If none are relevant, respond with 'NONE'."""
                
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
    # Enrich with knowledge base and Jira context if starting fresh
    enriched_context = {}
    if context and len(conversation_ctx.messages) <= 2:  # Early in conversation
        log_info("🔍 Enriching with KB and Jira context for ticket creation", "direct_processor")
        enriched_context = await _enrich_with_context(user_prompt, jira_service, ai_service, context)
    
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
        extract_prompt = f"""Extract ticket details from this entire conversation. Use ALL messages for context.

Full Conversation History:
{conversation_history}

Current Message: "{user_prompt}"

Already Collected: {json.dumps(conversation_ctx.collected_data)}
{context_info}

Rules:
- Analyze the ENTIRE conversation to understand what the user wants
- Extract information mentioned in ANY previous message
- Combine details from different messages
- If user said "that bug I mentioned" or "the issue from earlier", look back in history
- Use context to enhance descriptions but don't fabricate details

Extract (if mentioned anywhere in conversation):
- summary: brief title
- description: detailed description  
- issue_type: Bug/Story/Task/Epic
- priority: Critical/High/Medium/Low

Return ONLY JSON. If nothing found, return {{}}."""
        
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
    
    is_complete, missing_fields = validate_create_ticket_data(user_prompt, conversation_ctx.collected_data, context_hints)
    
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
    extract_prompt = f"""Extract update details from the current request and conversation history.

Conversation History:
{conversation_history}

Current Request: "{user_prompt}"

Already Collected Data: {json.dumps(conversation_ctx.collected_data)}
{ticket_context}
Analyze the ENTIRE conversation to extract any of these fields to update:
- ticket_key: the ticket ID
- status: new status (To Do, In Progress, Done, etc.)
- priority: new priority
- comment: comment to add (combine information from conversation if needed)
- summary: updated summary
- description: updated description

Return ONLY a JSON object, no other text:"""
    
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
    result = await search_tickets_tool(jira_service, context, user_prompt)
    
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
        
        analysis_prompt = f"""Analyze these JIRA tickets for: "{user_prompt}"

Tickets:
{tickets_summary}
{context_info}
{history_context}

Provide a concise summary:
- Count and overview
- Key tickets with status
- Notable patterns
- Brief actionable insights
{"- Reference to previous conversation context if relevant" if has_previous_context else ""}

Be direct and professional. Avoid verbosity."""
        
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
            result = await search_tickets_tool(jira_service, context, user_prompt)
            
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
