"""AI service for GenAI interactions."""
import httpx
from typing import Optional, Callable
from core.config import get_settings
from core.logging import log_info, log_error, log_debug
from utils.text import parse_json_response


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
        """Call PwC GenAI API."""
        if not all([
            self.settings.pwc_genai_api_key,
            self.settings.pwc_genai_bearer_token,
            self.settings.pwc_genai_endpoint_url
        ]):
            raise ValueError(
                "PwC GenAI credentials not configured. Please provide "
                "PWC_GENAI_API_KEY, PWC_GENAI_BEARER_TOKEN, and PWC_GENAI_ENDPOINT_URL."
            )
        
        request_body = {
            "model": "vertex_ai.gemini-2.0-flash",
            "prompt": prompt,
            "temperature": temperature,
            "top_p": 1,
            "presence_penalty": 0,
            "stream": False,
            "stream_options": None,
            "seed": 25,
            "stop": None,
        }
        
        headers = {
            "accept": "application/json",
            "API-Key": self.settings.pwc_genai_api_key,
            "Authorization": f"Bearer {self.settings.pwc_genai_bearer_token}",
            "Content-Type": "application/json",
        }
        
        log_info(f"Calling PwC GenAI (prompt length: {len(prompt)} chars)", "ai")
        log_debug(f"AI parameters: temp={temperature}, max_tokens={max_tokens}", "ai")
        log_debug(f"Using model: vertex_ai.gemini-2.0-flash", "ai")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            log_debug(f"Sending POST request to {self.settings.pwc_genai_endpoint_url}", "ai")
            response = await client.post(
                self.settings.pwc_genai_endpoint_url,
                json=request_body,
                headers=headers
            )
        
        log_debug(f"AI API response status: {response.status_code}", "ai")
        
        if response.status_code != 200:
            error_msg = f"PwC GenAI API Error: {response.status_code} - {response.text}"
            log_error(error_msg, "ai")
            raise ValueError(error_msg)
        
        result = response.json()
        log_debug(f"AI response structure: {list(result.keys())}", "ai")
        log_info("PwC GenAI response received successfully", "ai")
        
        # Extract content from response
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
            if "text" in choice:
                return choice["text"]
        if "text" in result:
            return result["text"]
        if "content" in result:
            return result["content"]
        
        raise ValueError("Unexpected response format from PwC GenAI API")
    
    def build_prompt(self, system_message: str, user_message: str) -> str:
        """Build a formatted prompt."""
        return f"System: {system_message}\n\nUser: {user_message}"


# Global AI service instance
ai_service = AIService()
