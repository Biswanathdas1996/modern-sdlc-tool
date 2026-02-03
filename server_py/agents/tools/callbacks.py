"""Callback handlers for JIRA agent."""
from langchain_core.callbacks import BaseCallbackHandler


class VerboseConsoleHandler(BaseCallbackHandler):
    """Callback handler to print agent steps to console."""
    
    def on_agent_action(self, action, **kwargs):
        """Print agent action."""
        print(f"\n🤖 [AGENT ACTION] Tool: {action.tool}")
        print(f"   Input: {action.tool_input}")
        print(f"   Log: {action.log}")
    
    def on_agent_finish(self, finish, **kwargs):
        """Print agent finish."""
        print(f"\n✅ [AGENT FINISH]")
        print(f"   Output: {finish.return_values}")
    
    def on_tool_start(self, serialized, input_str, **kwargs):
        """Print tool start."""
        tool_name = serialized.get("name", "Unknown")
        print(f"\n🔧 [TOOL START] {tool_name}")
        print(f"   Input: {input_str}")
    
    def on_tool_end(self, output, **kwargs):
        """Print tool output."""
        print(f"   Output: {output[:200]}{'...' if len(str(output)) > 200 else ''}")
    
    def on_tool_error(self, error, **kwargs):
        """Print tool error."""
        print(f"   ❌ Error: {error}")
    
    def on_llm_start(self, serialized, prompts, **kwargs):
        """Print LLM start."""
        print(f"\n💭 [LLM CALL] Generating response...")
    
    def on_llm_end(self, response, **kwargs):
        """Print LLM end."""
        print(f"   ✓ Response generated")
