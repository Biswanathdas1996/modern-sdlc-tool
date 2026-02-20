"""Slim orchestrator for JIRA agent with LangChain and direct processing."""
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

from services.jira_service import JiraService
from services.ai_service import AIService
from services.langchain_llm import PwCGenAILLM
from core.logging import log_info, log_error
from .tools import TicketToolsContext, create_jira_tools
from .utils import handle_parsing_error, analyze_intent
from .tools.direct_processor import direct_process
from prompts import prompt_loader
from .helpers.conversation_manager import ConversationContext


class JiraAgent:

    def __init__(self):
        self.jira_service = JiraService()
        self.ai_service = AIService()
        self.llm = PwCGenAILLM(temperature=0.2, max_tokens=6096)
        self.context = TicketToolsContext()
        self.tools = create_jira_tools(self.jira_service, self.context)
        self.agent = self._create_agent() if HAS_LANGCHAIN_AGENTS else None

    def _create_agent(self):
        prompt_template = prompt_loader.get_prompt('jira_agent.yml', 'agent_prompt')
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["input", "tools", "tool_names", "agent_scratchpad"]
        )
        agent = create_react_agent(llm=self.llm, tools=self.tools, prompt=prompt)
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=handle_parsing_error,
            max_iterations=5,
            return_intermediate_steps=True
        )

    async def process_query(self, user_prompt: str) -> Dict[str, Any]:
        """Legacy single-turn processing method."""
        try:
            log_info(f"Processing query (legacy): {user_prompt}", "jira_agent")
            intent = analyze_intent(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")

            try:
                if not self.agent:
                    raise Exception("LangChain agent not available, using direct processing")
                result = await self._run_agent(user_prompt)
                agent_output = result.get("output", "")

                if agent_output and len(agent_output) > 20:
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
                return await direct_process(user_prompt, intent, self.jira_service, self.ai_service, self.context)

        except Exception as e:
            log_error(f"Error processing query", "jira_agent", e)
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
        """Interactive multi-turn processing with smart information gathering and memory."""
        try:
            log_info(f"Processing interactive query: {user_prompt}", "jira_agent")
            intent = analyze_intent(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")

            result = await direct_process(
                user_prompt, intent, self.jira_service, self.ai_service,
                self.context, conversation_ctx=conversation_ctx
            )

            if conversation_ctx:
                result["conversation_summary"] = conversation_ctx.get_summary()
                result["message_count"] = len(conversation_ctx.messages)

            return result

        except Exception as e:
            log_error(f"Error in interactive processing", "jira_agent", e)
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
        def run_sync():
            return self.agent.invoke({"input": query})
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_sync)
        return result


jira_agent = JiraAgent()
