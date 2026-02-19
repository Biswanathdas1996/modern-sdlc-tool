"""Centralized utility for PwC GenAI LLM calls.

This module provides a unified interface for making LLM calls to PwC GenAI
across the entire application. It supports both synchronous and asynchronous calls,
automatic continuation for long responses, and consistent error handling.

Usage:
    # Async call
    response = await call_pwc_genai_async(prompt, temperature=0.7, max_tokens=4096)
    
    # Sync call
    response = call_pwc_genai_sync(prompt, temperature=0.7, max_tokens=4096)
    
    # Build formatted prompt
    prompt = build_pwc_prompt(system_message="You are a helpful assistant", 
                              user_message="What is Python?")
"""

import os
import httpx
import requests
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class PWCLLMConfig:
    """Configuration for PwC GenAI API."""
    
    def __init__(self):
        self.api_key = os.getenv("PWC_GENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.bearer_token = os.getenv("PWC_GENAI_BEARER_TOKEN")
        self.endpoint_url = os.getenv("PWC_GENAI_ENDPOINT_URL") or os.getenv(
            "GEMINI_API_ENDPOINT",
            "https://genai-sharedservice-americas.pwc.com/completions"
        )
        self.default_model = "vertex_ai.gemini-2.0-flash"
        self.default_timeout = 180
    
    def validate(self):
        """Validate that required credentials are present."""
        if not self.api_key:
            raise ValueError(
                "PwC GenAI API key not configured. Please provide "
                "PWC_GENAI_API_KEY or GEMINI_API_KEY in your .env file."
            )


# Global configuration instance
_config = PWCLLMConfig()


def _build_request_body(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """Build the request body for PwC GenAI API."""
    return {
        "model": model or _config.default_model,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 1,
        "presence_penalty": 0,
        "stream": False,
        "stream_options": None,
        "seed": 25,
        "stop": None,
    }


def _build_headers() -> Dict[str, str]:
    """Build headers for PwC GenAI API request."""
    headers = {
        "accept": "application/json",
        "API-Key": _config.api_key,
        "Content-Type": "application/json",
    }
    
    if _config.bearer_token:
        headers["Authorization"] = f"Bearer {_config.bearer_token}"
    
    return headers


def _extract_text_from_response(result: Dict[str, Any]) -> str:
    """Extract text content from API response."""
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


def _get_finish_reason(result: Dict[str, Any]) -> Optional[str]:
    """Get finish reason from API response."""
    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0].get("finish_reason", "stop")
    return "stop"


async def call_pwc_genai_async(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    timeout: int = None,
    enable_continuation: bool = False,
    max_continuations: int = 3
) -> str:
    """
    Make an async call to PwC GenAI API.
    
    Args:
        prompt: The prompt to send to the LLM
        temperature: Sampling temperature (0.0 to 1.0)
        max_tokens: Maximum tokens in response
        model: Model to use (default: vertex_ai.gemini-2.0-flash)
        timeout: Request timeout in seconds (default: 180)
        enable_continuation: Whether to handle response continuation
        max_continuations: Maximum number of continuations to attempt
        
    Returns:
        str: The LLM response text
        
    Raises:
        ValueError: If credentials are not configured or API returns error
    """
    _config.validate()
    
    request_body = _build_request_body(prompt, temperature, max_tokens, model)
    headers = _build_headers()
    timeout_value = timeout or _config.default_timeout
    
    accumulated_text = ""
    original_prompt = prompt
    
    attempts = max_continuations + 1 if enable_continuation else 1
    
    for attempt in range(attempts):
        if attempt > 0:
            # Build continuation prompt
            continuation_prompt = (
                f"{original_prompt}\n\n"
                f"[CONTINUATION] The previous response was cut off. Here is what was generated so far:\n"
                f"---\n{accumulated_text[-2000:]}\n---\n"
                f"Please continue from where you left off. Do not repeat what was already generated."
            )
            request_body["prompt"] = continuation_prompt
        
        async with httpx.AsyncClient(timeout=timeout_value) as client:
            response = await client.post(
                _config.endpoint_url,
                json=request_body,
                headers=headers
            )
        
        if response.status_code != 200:
            raise ValueError(
                f"PwC GenAI API Error: {response.status_code} - {response.text}"
            )
        
        result = response.json()
        chunk = _extract_text_from_response(result)
        accumulated_text += chunk
        
        # Check if we need continuation
        if enable_continuation:
            finish_reason = _get_finish_reason(result)
            if finish_reason != "length":
                break
        else:
            break
    
    return accumulated_text


def call_pwc_genai_sync(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    timeout: int = None,
    enable_continuation: bool = True,
    max_continuations: int = 3
) -> str:
    """
    Make a synchronous call to PwC GenAI API with automatic continuation support.
    
    Args:
        prompt: The prompt to send to the LLM
        temperature: Sampling temperature (0.0 to 1.0)
        max_tokens: Maximum tokens in response
        model: Model to use (default: vertex_ai.gemini-2.0-flash)
        timeout: Request timeout in seconds (default: 180)
        enable_continuation: Whether to handle response continuation
        max_continuations: Maximum number of continuations to attempt
        
    Returns:
        str: The LLM response text
        
    Raises:
        ValueError: If credentials are not configured or API returns error
    """
    _config.validate()
    
    request_body = _build_request_body(prompt, temperature, max_tokens, model)
    headers = _build_headers()
    timeout_value = timeout or _config.default_timeout
    
    accumulated_text = ""
    original_prompt = prompt
    
    attempts = max_continuations + 1 if enable_continuation else 1
    
    for attempt in range(attempts):
        if attempt > 0:
            # Build continuation prompt
            continuation_prompt = (
                f"{original_prompt}\n\n"
                f"[CONTINUATION] The previous response was cut off. Here is what was generated so far:\n"
                f"---\n{accumulated_text[-2000:]}\n---\n"
                f"Please continue from where you left off. Do not repeat what was already generated."
            )
            request_body["prompt"] = continuation_prompt
        
        response = requests.post(
            _config.endpoint_url,
            json=request_body,
            headers=headers,
            timeout=timeout_value
        )
        
        if response.status_code != 200:
            raise ValueError(
                f"PwC GenAI API Error: {response.status_code} - {response.text}"
            )
        
        result = response.json()
        chunk = _extract_text_from_response(result)
        accumulated_text += chunk
        
        # Check if we need continuation
        if enable_continuation:
            finish_reason = _get_finish_reason(result)
            if finish_reason != "length":
                break
        else:
            break
    
    return accumulated_text


def build_pwc_prompt(system_message: str, user_message: str) -> str:
    """
    Build a formatted prompt with system and user messages.
    
    Args:
        system_message: The system instruction
        user_message: The user's message
        
    Returns:
        str: Formatted prompt
    """
    return f"System: {system_message}\n\nUser: {user_message}"


def get_pwc_config() -> PWCLLMConfig:
    """
    Get the current PWC LLM configuration.
    
    Returns:
        PWCLLMConfig: The configuration instance
    """
    return _config


# Convenience exports
__all__ = [
    'call_pwc_genai_async',
    'call_pwc_genai_sync',
    'build_pwc_prompt',
    'get_pwc_config',
    'PWCLLMConfig'
]
