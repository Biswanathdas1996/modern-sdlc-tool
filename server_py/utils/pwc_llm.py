"""Centralized utility for PwC GenAI LLM calls.

This module provides a unified interface for making LLM calls to PwC GenAI
across the entire application. It supports both synchronous and asynchronous calls,
automatic continuation for long responses, and consistent error handling.

Model selection is driven by llm_config.yml via the `task_name` parameter.
Pass a task name (e.g. "brd_generation") to automatically use the model,
temperature and max_tokens defined in the YAML config.

Usage:
    # Task-based call (reads model from llm_config.yml)
    response = await call_pwc_genai_async(prompt, task_name="brd_generation")

    # Manual override still works
    response = await call_pwc_genai_async(prompt, model="azure.gpt-5.2", temperature=0.2)
    
    # Sync call
    response = call_pwc_genai_sync(prompt, task_name="unit_test_generation")
    
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
from core.logging import log_debug
from core.langfuse import start_generation, flush as langfuse_flush

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
        self.default_model = "vertex_ai.gemini-2.5-flash-image"
        self.default_timeout = 180
    
    def validate(self):
        """Validate that required credentials are present."""
        if not self.api_key:
            raise ValueError(
                "PwC GenAI API key not configured. Please provide "
                "PWC_GENAI_API_KEY or GEMINI_API_KEY in your .env file."
            )


_config = PWCLLMConfig()


def _resolve_task_config(task_name: Optional[str] = None):
    """Resolve model/temperature/max_tokens from llm_config.yml for a task."""
    if not task_name:
        return None
    try:
        from core.llm_config import get_llm_config
        return get_llm_config().get(task_name)
    except Exception:
        return None


def _build_request_body(
    prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 6096,
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
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    enable_continuation: bool = False,
    max_continuations: int = 3,
    task_name: Optional[str] = None,
    user_input: Optional[str] = None,
) -> str:
    """
    Make an async call to PwC GenAI API.
    
    Args:
        prompt: The full assembled prompt (system + history + current query)
        temperature: Sampling temperature (0.0-1.0). None = use config/defaults
        max_tokens: Maximum tokens in response. None = use config/defaults
        model: Model to use. None = resolved from llm_config.yml
        timeout: Request timeout in seconds. None = use config/defaults
        enable_continuation: Whether to handle response continuation
        max_continuations: Maximum number of continuations to attempt
        task_name: Key in llm_config.yml to auto-resolve model/temp/tokens
        user_input: Raw current user message (guardrails keyword check scans
                    only this so conversation history does not cause false blocks)
        
    Returns:
        str: The LLM response text
        
    Raises:
        ValueError: If credentials are not configured or API returns error
    """
    _config.validate()

    task_cfg = _resolve_task_config(task_name)
    if task_cfg:
        model = model or task_cfg.model
        temperature = temperature if temperature is not None else task_cfg.temperature
        max_tokens = max_tokens if max_tokens is not None else task_cfg.max_tokens
        timeout = timeout if timeout is not None else task_cfg.timeout

    temperature = temperature if temperature is not None else 0.2
    max_tokens = max_tokens if max_tokens is not None else 6096
    resolved_model = model or _config.default_model
    log_debug(
        f"[async] task={task_name or 'adhoc'} model={resolved_model} "
        f"temp={temperature} max_tokens={max_tokens}",
        "pwc_llm",
    )

    # --- NeMo Guardrails: screen every prompt before it reaches the LLM ---
    # Lazy import avoids circular dependency:
    # core.guardrails → services.langchain_llm → utils.pwc_llm
    try:
        from core.guardrails import check_input_async as _guardrails_check  # noqa: PLC0415
        await _guardrails_check(prompt, task_name, user_input)
    except Exception as _gr_exc:
        # Re-raise GuardrailsViolationError; swallow any other guardrails init errors
        from core.guardrails import GuardrailsViolationError as _GVE  # noqa: PLC0415
        if isinstance(_gr_exc, _GVE):
            raise
        log_debug(f"Guardrails check skipped due to error: {_gr_exc}", "pwc_llm")

    # --- Langfuse generation span ---
    generation = start_generation(
        task_name=task_name or "adhoc",
        model=resolved_model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata={"continuation": enable_continuation},
    )

    request_body = _build_request_body(prompt, temperature, max_tokens, model)
    headers = _build_headers()
    timeout_value = timeout or _config.default_timeout
    
    accumulated_text = ""
    original_prompt = prompt
    
    attempts = max_continuations + 1 if enable_continuation else 1
    
    try:
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

      generation.end(output=accumulated_text[:8000])
      langfuse_flush()
    except Exception as _exc:
      generation.end(output=f"ERROR: {_exc}")
      langfuse_flush()
      raise

    return accumulated_text


def call_pwc_genai_sync(
    prompt: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    enable_continuation: bool = True,
    max_continuations: int = 3,
    task_name: Optional[str] = None,
    user_input: Optional[str] = None,
) -> str:
    """
    Make a synchronous call to PwC GenAI API with automatic continuation support.
    
    Args:
        prompt: The full assembled prompt (system + history + current query)
        temperature: Sampling temperature (0.0-1.0). None = use config/defaults
        max_tokens: Maximum tokens in response. None = use config/defaults
        model: Model to use. None = resolved from llm_config.yml
        timeout: Request timeout in seconds. None = use config/defaults
        enable_continuation: Whether to handle response continuation
        max_continuations: Maximum number of continuations to attempt
        task_name: Key in llm_config.yml to auto-resolve model/temp/tokens
        user_input: Raw current user message (guardrails keyword check scans
                    only this so conversation history does not cause false blocks)
        
    Returns:
        str: The LLM response text
        
    Raises:
        ValueError: If credentials are not configured or API returns error
    """
    _config.validate()

    task_cfg = _resolve_task_config(task_name)
    if task_cfg:
        model = model or task_cfg.model
        temperature = temperature if temperature is not None else task_cfg.temperature
        max_tokens = max_tokens if max_tokens is not None else task_cfg.max_tokens
        timeout = timeout if timeout is not None else task_cfg.timeout

    temperature = temperature if temperature is not None else 0.2
    max_tokens = max_tokens if max_tokens is not None else 6096
    resolved_model = model or _config.default_model
    log_debug(
        f"[sync] task={task_name or 'adhoc'} model={resolved_model} "
        f"temp={temperature} max_tokens={max_tokens}",
        "pwc_llm",
    )

    # --- NeMo Guardrails: screen every prompt before it reaches the LLM ---
    # Lazy import avoids circular dependency:
    # core.guardrails → services.langchain_llm → utils.pwc_llm
    try:
        from core.guardrails import check_input_sync as _guardrails_check_sync  # noqa: PLC0415
        _guardrails_check_sync(prompt, task_name, user_input)
    except Exception as _gr_exc:
        from core.guardrails import GuardrailsViolationError as _GVE  # noqa: PLC0415
        if isinstance(_gr_exc, _GVE):
            raise
        log_debug(f"Guardrails check skipped due to error: {_gr_exc}", "pwc_llm")

    # --- Langfuse generation span ---
    generation = start_generation(
        task_name=task_name or "adhoc",
        model=resolved_model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata={"continuation": enable_continuation},
    )

    request_body = _build_request_body(prompt, temperature, max_tokens, model)
    headers = _build_headers()
    timeout_value = timeout or _config.default_timeout
    
    accumulated_text = ""
    original_prompt = prompt
    
    attempts = max_continuations + 1 if enable_continuation else 1
    
    try:
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

      generation.end(output=accumulated_text[:8000])
      langfuse_flush()
    except Exception as _exc:
      generation.end(output=f"ERROR: {_exc}")
      langfuse_flush()
      raise

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
