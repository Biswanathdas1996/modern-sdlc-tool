"""Production-ready orchestrator for JIRA agent with LangChain and direct processing.

Improvements over prototype:
- Input validation & sanitization
- Structured error handling with categorized exceptions
- Execution timeouts to prevent runaway agent loops
- Request-level metrics (latency, intent distribution)
- Rate limiting hooks (enforced at API layer)
- Graceful degradation: agent -> direct processing -> error response
"""
import asyncio
import time
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
from core.logging import log_info, log_error, log_warning
from core.llm_config import get_llm_config
from .tools import TicketToolsContext, create_jira_tools
from .utils import (
    handle_parsing_error,
    analyze_intent,
    analyze_intent_with_llm,
    validate_prompt,
    InputValidationError,
)
from .tools.direct_processor import direct_process
from prompts import prompt_loader
from .helpers.conversation_manager import ConversationContext
from .utils.langfuse_integration import (
    get_langfuse_handler,
    create_trace,
    flush as langfuse_flush,
    shutdown as langfuse_shutdown,
)

# --- Configuration constants ---
AGENT_MAX_ITERATIONS = 5
AGENT_MAX_EXECUTION_TIME = 120  # seconds
AGENT_RUN_TIMEOUT = 90  # seconds — asyncio timeout for a single _run_agent call


class JiraAgent:
    """Production-grade JIRA agent orchestrator.

    Wraps LangChain ``AgentExecutor`` with:
    - Input validation before any processing
    - Hard timeout on agent execution
    - Automatic fallback to direct (non-agent) processing
    - Structured, consistent response envelopes
    """

    def __init__(self):
        self.jira_service = JiraService()
        self.ai_service = AIService()
        _jira_cfg = get_llm_config().get("jira_agent")
        self.llm = PwCGenAILLM(
            temperature=_jira_cfg.temperature,
            max_tokens=_jira_cfg.max_tokens,
            task_name="jira_agent",
        )
        self.context = TicketToolsContext()
        self.tools = create_jira_tools(self.jira_service, self.context)
        self.agent = self._create_agent() if HAS_LANGCHAIN_AGENTS else None

        # Simple in-process metrics counters (swap for Prometheus/StatsD in prod)
        self._metrics: Dict[str, int] = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "agent_fallbacks": 0,
            "validation_errors": 0,
        }

    # ------------------------------------------------------------------ #
    # Agent construction
    # ------------------------------------------------------------------ #

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
            max_iterations=AGENT_MAX_ITERATIONS,
            max_execution_time=AGENT_MAX_EXECUTION_TIME,
            return_intermediate_steps=True,
        )

    # ------------------------------------------------------------------ #
    # Public API — legacy single-turn
    # ------------------------------------------------------------------ #

    async def process_query(self, user_prompt: str) -> Dict[str, Any]:
        """Legacy single-turn processing method with validation & metrics."""
        start = time.monotonic()
        self._metrics["requests_total"] += 1

        try:
            # --- Input validation ---
            user_prompt = validate_prompt(user_prompt)

            log_info(f"Processing query (legacy): {user_prompt[:120]}", "jira_agent")
            intent = analyze_intent(user_prompt)
            if intent["action"].value == "unknown":
                intent = await analyze_intent_with_llm(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")

            try:
                if not self.agent:
                    raise RuntimeError("LangChain agent not available, using direct processing")

                result = await self._run_agent(
                    user_prompt,
                    trace_metadata={"intent": intent["action"].value, "mode": "legacy"},
                )
                agent_output = result.get("output", "")

                if agent_output and len(agent_output) > 20:
                    self._metrics["requests_success"] += 1
                    return {
                        "success": True,
                        "prompt": user_prompt,
                        "intent": intent['action'].value,
                        "response": agent_output,
                        "tickets": self.context.last_search_results,
                        "intermediate_steps": result.get("intermediate_steps", []),
                        "duration_ms": self._elapsed_ms(start),
                    }
                else:
                    raise RuntimeError("Agent produced empty or minimal response")

            except Exception as agent_error:
                self._metrics["agent_fallbacks"] += 1
                log_warning(
                    f"Agent error, falling back to direct processing: {agent_error}",
                    "jira_agent",
                )
                result = await direct_process(
                    user_prompt, intent, self.jira_service, self.ai_service, self.context
                )
                result["duration_ms"] = self._elapsed_ms(start)
                self._metrics["requests_success"] += 1
                return result

        except InputValidationError as ve:
            self._metrics["validation_errors"] += 1
            log_warning(f"Input validation failed: {ve}", "jira_agent")
            return self._error_response(user_prompt, str(ve), start)

        except Exception as e:
            self._metrics["requests_failed"] += 1
            log_error("Error processing query", "jira_agent", e)
            return self._error_response(user_prompt, str(e), start)

    # ------------------------------------------------------------------ #
    # Public API — interactive multi-turn
    # ------------------------------------------------------------------ #

    async def process_query_interactive(
        self,
        user_prompt: str,
        conversation_ctx: Optional[ConversationContext] = None,
        context_data: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Interactive multi-turn processing with validation, timeouts, and metrics."""
        start = time.monotonic()
        self._metrics["requests_total"] += 1

        if project_id:
            self.context.project_id = project_id

        try:
            # --- Input validation ---
            user_prompt = validate_prompt(user_prompt)

            log_info(f"Processing interactive query: {user_prompt[:120]}", "jira_agent")
            intent = analyze_intent(user_prompt)
            if intent["action"].value == "unknown":
                intent = await analyze_intent_with_llm(user_prompt)
            log_info(f"Detected intent: {intent['action'].value}", "jira_agent")

            result = await direct_process(
                user_prompt, intent, self.jira_service, self.ai_service,
                self.context, conversation_ctx=conversation_ctx,
            )

            # --- Trace direct processing path in Langfuse ---
            session_id_val = conversation_ctx.session_id if conversation_ctx else None
            trace = create_trace(
                name="jira-agent-interactive",
                session_id=session_id_val,
                metadata={
                    "intent": intent["action"].value,
                    "mode": "interactive",
                    "success": result.get("success", False),
                },
                tags=["jira-agent", "interactive", intent["action"].value],
            )
            if trace:
                trace.update(output=result.get("response", "")[:500])

            if conversation_ctx:
                result["conversation_summary"] = conversation_ctx.get_summary()
                result["message_count"] = len(conversation_ctx.messages)

            result["duration_ms"] = self._elapsed_ms(start)
            self._metrics["requests_success"] += 1
            return result

        except InputValidationError as ve:
            self._metrics["validation_errors"] += 1
            log_warning(f"Input validation failed: {ve}", "jira_agent")
            return {
                "success": False,
                "state": "initial",
                "session_id": conversation_ctx.session_id if conversation_ctx else "unknown",
                "prompt": user_prompt,
                "error": str(ve),
                "response": f"Invalid input: {ve}",
                "tickets": [],
                "duration_ms": self._elapsed_ms(start),
            }

        except Exception as e:
            self._metrics["requests_failed"] += 1
            log_error("Error in interactive processing", "jira_agent", e)
            return {
                "success": False,
                "state": "initial",
                "session_id": conversation_ctx.session_id if conversation_ctx else "unknown",
                "prompt": user_prompt,
                "error": str(e),
                "response": "I encountered an error processing your request. Please try rephrasing.",
                "tickets": [],
                "duration_ms": self._elapsed_ms(start),
            }

    # ------------------------------------------------------------------ #
    # Agent execution with timeout
    # ------------------------------------------------------------------ #

    async def _run_agent(
        self,
        query: str,
        trace_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the LangChain agent with a hard asyncio timeout and Langfuse tracing."""

        # Build Langfuse callback handler for this invocation
        langfuse_handler = get_langfuse_handler(
            trace_name="jira-agent-run",
            tags=["jira-agent", "langchain"],
            metadata=trace_metadata or {},
        )
        callbacks = [langfuse_handler] if langfuse_handler else []

        def run_sync():
            return self.agent.invoke(
                {"input": query},
                config={"callbacks": callbacks} if callbacks else {},
            )

        loop = asyncio.get_event_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, run_sync),
                timeout=AGENT_RUN_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            log_error(
                f"Agent execution timed out after {AGENT_RUN_TIMEOUT}s",
                "jira_agent",
            )
            raise RuntimeError(
                f"Agent execution timed out after {AGENT_RUN_TIMEOUT} seconds"
            )
        finally:
            # Ensure Langfuse events are flushed even on error/timeout
            langfuse_flush()

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #

    def get_metrics(self) -> Dict[str, Any]:
        """Return a snapshot of in-process metrics."""
        return dict(self._metrics)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    @staticmethod
    def _error_response(prompt: str, error: str, start: float) -> Dict[str, Any]:
        return {
            "success": False,
            "prompt": prompt,
            "error": error,
            "response": "I encountered an error processing your request. Please try rephrasing.",
            "tickets": [],
            "duration_ms": int((time.monotonic() - start) * 1000),
        }


jira_agent = JiraAgent()
