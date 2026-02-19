"""
Robust LangChain-based JIRA Agent with intelligent query analysis and interactive info gathering.
Supports: Search, Create, Update tickets, chained operations, and multi-turn conversations.
"""
import asyncio
from typing import Dict, Any, Optional

try:
    from langchain.agents import AgentExecutor, create_react_agent
    from langchain_core.prompts import PromptTemplate
    HAS_LANGCHAIN_AGENTS = True
except ImportError:
    try:
        from langchain_community.agents import AgentExecutor, create_react_agent
        from langchain_core.prompts import PromptTemplate
        HAS_LANGCHAIN_AGENTS = True
    except ImportError:
        HAS_LANGCHAIN_AGENTS = False
        AgentExecutor = None
        create_react_agent = None
        PromptTemplate = None
        # LangChain AgentExecutor not available - will use direct processing only

from services.jira_service import JiraService
from services.ai_service import AIService
from services.langchain_llm import PwCGenAILLM
from core.logging import log_info, log_error
from .tools import TicketToolsContext, create_jira_tools
from .utils import handle_parsing_error, analyze_intent
from .direct_processor import direct_process
from .prompts import prompt_loader
from .conversation_manager import ConversationContext


class JiraAgent:
    
    def __init__(self):
        """Initialize the JIRA agent with LangChain components."""
        self.jira_service = JiraService()
        self.ai_service = AIService()
        self.llm = PwCGenAILLM(temperature=0.2, max_tokens=4096)
        
        self.context = TicketToolsContext()
        
        self.tools = create_jira_tools(self.jira_service, self.context)
        self.agent = self._create_agent() if HAS_LANGCHAIN_AGENTS else None
        
    def _create_agent(self):
        """Create the LangChain ReAct agent with robust parsing."""
        
        # Load prompt from YAML file
        prompt_template = prompt_loader.get_prompt('jira_agent.yml', 'agent_prompt')
        
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["input", "tools", "tool_names", "agent_scratchpad"]
        )
        
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=handle_parsing_error,
            max_iterations=5,
            return_intermediate_steps=True
        )
    
    async def process_query(self, user_prompt: str) -> Dict[str, Any]:
        """
        Legacy single-turn processing method.
        Maintained for backward compatibility with existing integrations.
        
        For new integrations, use process_query_interactive() instead.
        """
        try:
            log_info(f"Processing query (legacy): {user_prompt}", "jira_agent")
            
            # Analyze intent first for logging and fallback
            intent = analyze_intent(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")
            if intent.get('ticket_key'):
                log_debug(f"Ticket key found: {intent['ticket_key']}", "jira_agent")
            
            # Try LangChain agent first (if available)
            try:
                if not self.agent:
                    raise Exception("LangChain agent not available, using direct processing")
                log_debug("Running LangChain Agent", "jira_agent")
                result = await self._run_agent(user_prompt)
                agent_output = result.get("output", "")
                
                # Check if agent produced a meaningful response
                if agent_output and len(agent_output) > 20:
                    print(f"\n{'='*80}")
                    print(f"✅ JIRA AGENT COMPLETED")
                    print(f"{'='*80}\n")
                    
                    return {
                        "success": True,
                        "prompt": user_prompt,
                        "intent": intent['action'].value,
                        "response": agent_output,
                        "tickets": self.context.last_search_results,
                        "intermediate_steps": result.get("intermediate_steps", [])
                    }
                else:
                    raise Exception("Agent produced empty or minimal response")
                    
            except Exception as agent_error:
                log_error(f"Agent error, falling back to direct processing: {agent_error}", "jira_agent")
                print(f"⚠️ Agent encountered issue, using direct processing...")
                
                # Fallback to direct processing without conversation context
                return await direct_process(user_prompt, intent, self.jira_service, self.ai_service, self.context)
            
        except Exception as e:
            log_error(f"Error processing query", "jira_agent", e)
            print(f"\n❌ ERROR: {str(e)}\n")
            return {
                "success": False,
                "prompt": user_prompt,
                "error": str(e),
                "response": f"I encountered an error: {str(e)}. Please try rephrasing your request.",
                "tickets": []
            }
    
    async def process_query_interactive(
        self,
        user_prompt: str,
        conversation_ctx: Optional[ConversationContext] = None,
        context_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Interactive multi-turn processing with smart information gathering and memory.
        
        This method maintains conversation context and remembers previous interactions
        within the same session_id.
        
        Args:
            user_prompt: User's natural language query
            conversation_ctx: Conversation context for multi-turn interactions with memory
            context_data: Additional context data from previous turns
            
        Returns:
            Response dictionary with state, missing_fields, collected_data, and conversation history
        """
        try:
            log_info(f"🚀 Processing interactive query: {user_prompt}", "jira_agent")
            print(f"🤖 JIRA AGENT - Interactive Processing")
            print(f"Query: {user_prompt}")
            if conversation_ctx:
                print(f"Session: {conversation_ctx.session_id}")
                print(f"State: {conversation_ctx.state.value}")
                print(f"Context: {conversation_ctx.get_summary()}\n")
            
            # Analyze intent
            intent = analyze_intent(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")
            print(f"🎯 Detected Intent: {intent['action'].value}")
            if intent.get('ticket_key'):
                print(f"🎫 Ticket Key Found: {intent['ticket_key']}")
            
            # Use direct processor with conversation context for interactive mode
            # This allows for information gathering and multi-turn conversations
            result = await direct_process(
                user_prompt,
                intent,
                self.jira_service,
                self.ai_service,
                self.context,
                conversation_ctx=conversation_ctx
            )
            
            # Add conversation summary to result
            if conversation_ctx:
                result["conversation_summary"] = conversation_ctx.get_summary()
                result["message_count"] = len(conversation_ctx.messages)
            
            if result.get("success"):
                print(f"\n{'='*80}")
                print(f"✅ JIRA AGENT COMPLETED")
                print(f"{'='*80}\n")
            else:
                state = result.get("state", "unknown")
                if state == "awaiting_info":
                    print(f"\n{'='*80}")
                    print(f"ℹ️ AWAITING USER INPUT")
                    print(f"{'='*80}\n")
            
            return result
            
        except Exception as e:
            log_error(f"Error in interactive processing", "jira_agent", e)
            print(f"\n❌ ERROR: {str(e)}\n")
            return {
                "success": False,
                "state": "initial",
                "session_id": conversation_ctx.session_id if conversation_ctx else "unknown",
                "prompt": user_prompt,
                "error": str(e),
                "response": f"I encountered an error: {str(e)}. Please try rephrasing your request.",
                "tickets": []
            }
    
    async def _run_agent(self, query: str) -> Dict[str, Any]:
        """Run the LangChain agent asynchronously."""
        # The agent executor needs to run in sync context
        def run_sync():
            return self.agent.invoke({"input": query})
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_sync)
        
        return result


# Global instance
jira_agent = JiraAgent()
