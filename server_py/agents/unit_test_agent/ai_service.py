from typing import Optional
from utils.pwc_llm import call_pwc_genai_sync, build_pwc_prompt


class AIService:
    """Unit Test Agent AI Service using centralized PWC LLM utility."""
    
    def __init__(self):
        pass

    def call_genai(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None, task_name: str = "unit_test_generation") -> str:
        """Call PwC GenAI using centralized utility with continuation support."""
        return call_pwc_genai_sync(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_continuation=True,
            max_continuations=3,
            task_name=task_name,
        )
    
    def build_prompt(self, system_message: str, user_message: str) -> str:
        """Build a formatted prompt."""
        return build_pwc_prompt(system_message, user_message)


ai_service = AIService()
