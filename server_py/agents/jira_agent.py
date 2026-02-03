"""
Robust LangChain-based JIRA Agent with intelligent query analysis.
Supports: Search, Create, Update tickets, and chained operations (search -> update).
"""
import asyncio
from typing import Dict, Any

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from services.jira_service import JiraService
from services.ai_service import AIService
from services.langchain_llm import PwCGenAILLM
from core.logging import log_info, log_error
from .tools import TicketToolsContext, create_jira_tools
from .utils import handle_parsing_error, analyze_intent
from .direct_processor import direct_process
from .prompts import prompt_loader


class JiraAgent:
    
    def __init__(self):
        """Initialize the JIRA agent with LangChain components."""
        self.jira_service = JiraService()
        self.ai_service = AIService()
        self.llm = PwCGenAILLM(temperature=0.2, max_tokens=4096)
        
        # Context storage for chained operations
        self.context = TicketToolsContext()
        
        # Initialize tools and agent
        self.tools = create_jira_tools(self.jira_service, self.context)
        self.agent = self._create_agent()
        
    def _create_agent(self) -> AgentExecutor:
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
        try:
            log_info(f"🚀 Processing query: {user_prompt}", "jira_agent")
            print(f"🤖 JIRA AGENT - Processing Query")
            print(f"Query: {user_prompt}\n")
            
            # Analyze intent first for logging and fallback
            intent = analyze_intent(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")
            print(f"🎯 Detected Intent: {intent['action'].value}")
            if intent.get('ticket_key'):
                print(f"🎫 Ticket Key Found: {intent['ticket_key']}")
            
            # Try LangChain agent first
            try:
                print(f"\n🔧 Running LangChain Agent...")
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
                
                # Fallback to direct processing based on intent
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
