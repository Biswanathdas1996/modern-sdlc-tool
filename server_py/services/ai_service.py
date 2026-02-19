"""AI service for GenAI interactions."""
from typing import Optional, Callable
from core.config import get_settings
from core.logging import log_info, log_error, log_debug
from utils.text import parse_json_response
from utils.pwc_llm import call_pwc_genai_async, build_pwc_prompt


class AIService:
    """Service for AI/GenAI operations."""
    
    def __init__(self):
        self.settings = get_settings()
        
    async def call_genai(
        self, 
        prompt: str, 
        temperature: float = 0.7, 
        max_tokens: int = 4096
    ) -> str:
        """Call PwC GenAI API using centralized utility."""
        log_info(f"Calling PwC GenAI (prompt length: {len(prompt)} chars)", "ai")
        log_debug(f"AI parameters: temp={temperature}, max_tokens={max_tokens}", "ai")
        log_debug(f"Using model: vertex_ai.gemini-2.0-flash", "ai")
        
        try:
            response = await call_pwc_genai_async(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120
            )
            log_info("PwC GenAI response received successfully", "ai")
            return response
        except Exception as e:
            error_msg = f"PwC GenAI API Error: {str(e)}"
            log_error(error_msg, "ai")
            raise
    
    def build_prompt(self, system_message: str, user_message: str) -> str:
        """Build a formatted prompt."""
        return build_pwc_prompt(system_message, user_message)


# Global AI service instance
ai_service = AIService()
