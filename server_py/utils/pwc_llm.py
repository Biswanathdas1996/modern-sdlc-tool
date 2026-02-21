"""Centralized utility for PwC GenAI LLM calls.

This module provides a unified interface for making LLM calls to PwC GenAI
across the entire application. It dynamically supports all model types:

  - Text / Multimodal completion (gemini, gpt, claude, grok)
  - Embeddings (text-embedding-005, gemini-embedding)
  - Audio transcription (whisper)

Model selection is driven by llm_config.yml via the `task_name` parameter.
Pass a task name (e.g. "brd_generation") to automatically use the model,
temperature and max_tokens defined in the YAML config.

Usage:
    # Task-based call (reads model from llm_config.yml)
    response = await call_pwc_genai_async(prompt, task_name="brd_generation")

    # Manual override still works
    response = await call_pwc_genai_async(prompt, model="azure.gpt-5.2", temperature=0.2)

    # Multimodal call with images
    response = await call_pwc_genai_async(prompt, task_name="repo_analysis", images=[image_bytes])

    # Embedding call
    vectors = await call_pwc_embedding_async(["hello world"], task_name="kb_embedding")

    # Audio transcription
    text = await call_pwc_transcribe_async(audio_bytes, task_name="audio_transcription")

    # Sync call
    response = call_pwc_genai_sync(prompt, task_name="unit_test_generation")

    # Build formatted prompt
    prompt = build_pwc_prompt(system_message="You are a helpful assistant",
                              user_message="What is Python?")
"""

import os
import json
import base64
import httpx
import requests
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from dotenv import load_dotenv
from core.logging import log_debug, log_info, log_error
from core.langfuse import start_generation, start_span, extract_usage, flush as langfuse_flush

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class ModelType(str, Enum):
    TEXT = "text"
    MULTIMODAL = "multimodal"
    EMBEDDING = "embedding"
    AUDIO = "audio"


_MODEL_TYPE_MAP = {
    "vertex_ai.gemini-2.5-flash-image": ModelType.MULTIMODAL,
    "vertex_ai.gemini-2.5-pro": ModelType.MULTIMODAL,
    "azure.gpt-5.2": ModelType.TEXT,
    "vertex_ai.anthropic.claude-sonnet-4-6": ModelType.TEXT,
    "azure.grok-4-fast-reasoning": ModelType.TEXT,
    "openai.whisper": ModelType.AUDIO,
    "vertex_ai.text-embedding-005": ModelType.EMBEDDING,
    "vertex_ai.gemini-embedding": ModelType.EMBEDDING,
}


def detect_model_type(model_name: str) -> ModelType:
    """Detect the model type from the model name.

    Uses an explicit lookup table first, then falls back to pattern matching
    so newly added models are handled gracefully.
    """
    if model_name in _MODEL_TYPE_MAP:
        return _MODEL_TYPE_MAP[model_name]

    name_lower = model_name.lower()
    if "whisper" in name_lower or "transcri" in name_lower:
        return ModelType.AUDIO
    if "embed" in name_lower:
        return ModelType.EMBEDDING
    if "gemini" in name_lower and ("image" in name_lower or "vision" in name_lower):
        return ModelType.MULTIMODAL
    return ModelType.TEXT


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

    def get_endpoint(self, model_type: ModelType) -> str:
        """Return the endpoint URL, adjusting for model type if needed.

        The PwC GenAI shared-service exposes different paths per capability:
          /completions   – text & multimodal completions (default)
          /embeddings    – embedding vectors
          /transcriptions – audio-to-text (whisper)

        If the env-var already contains a specific path we respect it;
        otherwise we swap the tail segment.
        """
        base = self.endpoint_url.rstrip("/")

        if model_type == ModelType.EMBEDDING:
            if base.endswith("/completions"):
                return base.rsplit("/completions", 1)[0] + "/embeddings"
            if not base.endswith("/embeddings"):
                return base + "/embeddings"
        elif model_type == ModelType.AUDIO:
            if base.endswith("/completions"):
                return base.rsplit("/completions", 1)[0] + "/transcriptions"
            if not base.endswith("/transcriptions"):
                return base + "/transcriptions"

        return base


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
    model: Optional[str] = None,
    images: Optional[List[bytes]] = None,
) -> Dict[str, Any]:
    """Build the request body for PwC GenAI API.

    For multimodal models, if `images` is provided the prompt is sent as a
    structured content array with text and inline image parts.
    """
    resolved_model = model or _config.default_model
    model_type = detect_model_type(resolved_model)

    if images and model_type == ModelType.MULTIMODAL:
        content_parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img_bytes in images:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        prompt_value: Any = content_parts
    else:
        prompt_value = prompt

    is_anthropic = "anthropic" in resolved_model.lower()

    body: Dict[str, Any] = {
        "model": resolved_model,
        "prompt": prompt_value,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "stream_options": None,
        "stop": None,
    }

    if not is_anthropic:
        body["top_p"] = 1
        body["presence_penalty"] = 0
        body["seed"] = 25

    return body


def _build_embedding_request_body(
    texts: List[str],
    model: str,
) -> Dict[str, Any]:
    """Build the request body for an embedding call."""
    return {
        "model": model,
        "input": texts,
    }


def _build_transcription_request_body(
    audio_data: bytes,
    model: str,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the request body for an audio transcription call."""
    body: Dict[str, Any] = {
        "model": model,
        "audio": base64.b64encode(audio_data).decode("utf-8"),
    }
    if language:
        body["language"] = language
    return body


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


def _extract_embeddings_from_response(result: Dict[str, Any]) -> List[List[float]]:
    """Extract embedding vectors from API response."""
    if "data" in result:
        return [item["embedding"] for item in sorted(result["data"], key=lambda x: x.get("index", 0))]
    if "embedding" in result:
        emb = result["embedding"]
        return [emb] if isinstance(emb[0], float) else emb
    if "embeddings" in result:
        return result["embeddings"]
    raise ValueError("Unexpected embedding response format from PwC GenAI API")


def _extract_transcription_from_response(result: Dict[str, Any]) -> str:
    """Extract transcription text from API response."""
    if "text" in result:
        return result["text"]
    if "transcription" in result:
        return result["transcription"]
    if "results" in result and len(result["results"]) > 0:
        return " ".join(r.get("text", "") for r in result["results"])
    raise ValueError("Unexpected transcription response format from PwC GenAI API")


def _get_finish_reason(result: Dict[str, Any]) -> Optional[str]:
    """Get finish reason from API response."""
    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0].get("finish_reason", "stop")
    return "stop"


# ============================================================================
# Text / Multimodal Completion
# ============================================================================

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
    images: Optional[List[bytes]] = None,
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
        images: Optional list of image bytes for multimodal models

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
    model_type = detect_model_type(resolved_model)

    if images and model_type != ModelType.MULTIMODAL:
        log_debug(
            f"[async] images provided but model {resolved_model} is not multimodal — images will be ignored",
            "pwc_llm",
        )
        images = None

    log_debug(
        f"[async] task={task_name or 'adhoc'} model={resolved_model} "
        f"type={model_type.value} temp={temperature} max_tokens={max_tokens}"
        + (f" images={len(images)}" if images else ""),
        "pwc_llm",
    )

    try:
        from core.guardrails import check_input_async as _guardrails_check
        await _guardrails_check(prompt, task_name, user_input)
    except Exception as _gr_exc:
        from core.guardrails import GuardrailsViolationError as _GVE
        if isinstance(_gr_exc, _GVE):
            raise
        log_debug(f"Guardrails check skipped due to error: {_gr_exc}", "pwc_llm")

    generation = start_generation(
        task_name=task_name or "adhoc",
        model=resolved_model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata={"continuation": enable_continuation, "model_type": model_type.value, "has_images": bool(images)},
    )

    request_body = _build_request_body(prompt, temperature, max_tokens, model, images=images)
    headers = _build_headers()
    endpoint = _config.get_endpoint(model_type)
    timeout_value = timeout or _config.default_timeout

    accumulated_text = ""
    original_prompt = prompt
    usage = None

    attempts = max_continuations + 1 if enable_continuation else 1

    try:
      for attempt in range(attempts):
        if attempt > 0:
            continuation_prompt = (
                f"{original_prompt}\n\n"
                f"[CONTINUATION] The previous response was cut off. Here is what was generated so far:\n"
                f"---\n{accumulated_text[-2000:]}\n---\n"
                f"Please continue from where you left off. Do not repeat what was already generated."
            )
            request_body["prompt"] = continuation_prompt

        async with httpx.AsyncClient(timeout=timeout_value) as client:
            response = await client.post(
                endpoint,
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
        usage = extract_usage(result)

        if enable_continuation:
            finish_reason = _get_finish_reason(result)
            if finish_reason != "length":
                break
        else:
            break

      end_kwargs: Dict[str, Any] = {"output": accumulated_text[:8000]}
      if usage:
          end_kwargs["usage"] = usage
      generation.end(**end_kwargs)
      langfuse_flush()
    except Exception as _exc:
      generation.end(output=f"ERROR: {_exc}", level="ERROR", status_message=str(_exc))
      langfuse_flush()
      raise

    return accumulated_text


async def call_pwc_genai_stream(
    prompt: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    task_name: Optional[str] = None,
    user_input: Optional[str] = None,
):
    """
    Async generator that streams text chunks from PwC GenAI API.

    Yields:
        str: Individual text chunks as they arrive from the API.
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
    model_type = detect_model_type(resolved_model)

    log_debug(
        f"[stream] task={task_name or 'adhoc'} model={resolved_model} "
        f"type={model_type.value} temp={temperature} max_tokens={max_tokens}",
        "pwc_llm",
    )

    try:
        from core.guardrails import check_input_async as _guardrails_check
        await _guardrails_check(prompt, task_name, user_input)
    except Exception as _gr_exc:
        from core.guardrails import GuardrailsViolationError as _GVE
        if isinstance(_gr_exc, _GVE):
            raise
        log_debug(f"Guardrails check skipped due to error: {_gr_exc}", "pwc_llm")

    generation = start_generation(
        task_name=task_name or "adhoc_stream",
        model=resolved_model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata={"streaming": True, "model_type": model_type.value},
    )

    request_body = _build_request_body(prompt, temperature, max_tokens, model)
    request_body["stream"] = True
    headers = _build_headers()
    endpoint = _config.get_endpoint(model_type)
    timeout_value = timeout or _config.default_timeout

    accumulated_text = ""

    try:
        async with httpx.AsyncClient(timeout=timeout_value) as client:
            async with client.stream(
                "POST",
                endpoint,
                json=request_body,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise ValueError(
                        f"PwC GenAI API Error: {response.status_code} - {body.decode()}"
                    )

                content_type = response.headers.get("content-type", "")
                is_sse = "text/event-stream" in content_type
                got_chunks = False

                log_info(
                    f"[stream] Response content-type: {content_type} | is_sse: {is_sse}",
                    "pwc_llm",
                )

                buffer = ""
                chunk_count = 0
                async for raw_chunk in response.aiter_text():
                    buffer += raw_chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("data: "):
                            line = line[6:]

                        if line == "[DONE]":
                            break

                        try:
                            chunk_data = json.loads(line)
                            delta_text = ""
                            if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                choice = chunk_data["choices"][0]
                                delta = choice.get("delta", {})
                                delta_text = delta.get("content", "")
                                if not delta_text:
                                    delta_text = choice.get("text", "")
                                if not delta_text:
                                    msg = choice.get("message", {})
                                    delta_text = msg.get("content", "")
                            elif "text" in chunk_data:
                                delta_text = chunk_data["text"]
                            elif "content" in chunk_data:
                                delta_text = chunk_data["content"]

                            if delta_text:
                                got_chunks = True
                                chunk_count += 1
                                accumulated_text += delta_text
                                yield delta_text
                        except json.JSONDecodeError:
                            continue

                if buffer.strip():
                    try:
                        chunk_data = json.loads(buffer.strip())
                        text = _extract_text_from_response(chunk_data)
                        if text and not got_chunks:
                            log_info(
                                f"[stream] Non-streaming fallback: got full response ({len(text)} chars)",
                                "pwc_llm",
                            )
                            accumulated_text += text
                            yield text
                    except (json.JSONDecodeError, ValueError):
                        pass

                log_info(
                    f"[stream] Complete: {chunk_count} SSE chunks, "
                    f"got_chunks={got_chunks}, total={len(accumulated_text)} chars",
                    "pwc_llm",
                )

        generation.end(output=accumulated_text[:8000])
        langfuse_flush()
    except Exception as _exc:
        generation.end(output=f"ERROR: {_exc}", level="ERROR", status_message=str(_exc))
        langfuse_flush()
        raise


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
    images: Optional[List[bytes]] = None,
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
        images: Optional list of image bytes for multimodal models

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
    model_type = detect_model_type(resolved_model)

    if images and model_type != ModelType.MULTIMODAL:
        log_debug(
            f"[sync] images provided but model {resolved_model} is not multimodal — images will be ignored",
            "pwc_llm",
        )
        images = None

    log_debug(
        f"[sync] task={task_name or 'adhoc'} model={resolved_model} "
        f"type={model_type.value} temp={temperature} max_tokens={max_tokens}"
        + (f" images={len(images)}" if images else ""),
        "pwc_llm",
    )

    try:
        from core.guardrails import check_input_sync as _guardrails_check_sync
        _guardrails_check_sync(prompt, task_name, user_input)
    except Exception as _gr_exc:
        from core.guardrails import GuardrailsViolationError as _GVE
        if isinstance(_gr_exc, _GVE):
            raise
        log_debug(f"Guardrails check skipped due to error: {_gr_exc}", "pwc_llm")

    generation = start_generation(
        task_name=task_name or "adhoc",
        model=resolved_model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata={"continuation": enable_continuation, "model_type": model_type.value, "has_images": bool(images)},
    )

    request_body = _build_request_body(prompt, temperature, max_tokens, model, images=images)
    headers = _build_headers()
    endpoint = _config.get_endpoint(model_type)
    timeout_value = timeout or _config.default_timeout

    accumulated_text = ""
    original_prompt = prompt
    usage = None

    attempts = max_continuations + 1 if enable_continuation else 1

    try:
      for attempt in range(attempts):
        if attempt > 0:
            continuation_prompt = (
                f"{original_prompt}\n\n"
                f"[CONTINUATION] The previous response was cut off. Here is what was generated so far:\n"
                f"---\n{accumulated_text[-2000:]}\n---\n"
                f"Please continue from where you left off. Do not repeat what was already generated."
            )
            request_body["prompt"] = continuation_prompt

        response = requests.post(
            endpoint,
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
        usage = extract_usage(result)

        if enable_continuation:
            finish_reason = _get_finish_reason(result)
            if finish_reason != "length":
                break
        else:
            break

      end_kwargs: Dict[str, Any] = {"output": accumulated_text[:8000]}
      if usage:
          end_kwargs["usage"] = usage
      generation.end(**end_kwargs)
      langfuse_flush()
    except Exception as _exc:
      generation.end(output=f"ERROR: {_exc}", level="ERROR", status_message=str(_exc))
      langfuse_flush()
      raise

    return accumulated_text


# ============================================================================
# Embedding
# ============================================================================

async def call_pwc_embedding_async(
    texts: List[str],
    model: Optional[str] = None,
    task_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> List[List[float]]:
    """
    Generate embedding vectors via PwC GenAI API.

    Args:
        texts: List of strings to embed
        model: Embedding model name. Defaults to vertex_ai.text-embedding-005
        task_name: Key in llm_config.yml to resolve model
        timeout: Request timeout in seconds

    Returns:
        List of embedding vectors (one per input text)
    """
    _config.validate()

    task_cfg = _resolve_task_config(task_name)
    if task_cfg:
        model = model or task_cfg.model
        timeout = timeout if timeout is not None else task_cfg.timeout

    resolved_model = model or "vertex_ai.text-embedding-005"
    timeout_value = timeout or _config.default_timeout
    endpoint = _config.get_endpoint(ModelType.EMBEDDING)

    log_debug(
        f"[embedding] task={task_name or 'adhoc'} model={resolved_model} texts={len(texts)}",
        "pwc_llm",
    )

    request_body = _build_embedding_request_body(texts, resolved_model)
    headers = _build_headers()

    span = start_span(
        name=f"embedding/{task_name or 'adhoc'}",
        input=f"texts={len(texts)}, model={resolved_model}, first={texts[0][:200] if texts else ''}",
        metadata={"model": resolved_model, "text_count": len(texts)},
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_value) as client:
            response = await client.post(endpoint, json=request_body, headers=headers)

        if response.status_code != 200:
            raise ValueError(f"PwC GenAI Embedding API Error: {response.status_code} - {response.text}")

        result = response.json()
        embeddings = _extract_embeddings_from_response(result)
        span.end(output=f"Generated {len(embeddings)} embeddings, dims={len(embeddings[0]) if embeddings else 0}")
        langfuse_flush()
        return embeddings
    except Exception as _exc:
        span.end(output=f"ERROR: {_exc}")
        langfuse_flush()
        raise


def call_pwc_embedding_sync(
    texts: List[str],
    model: Optional[str] = None,
    task_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> List[List[float]]:
    """
    Generate embedding vectors via PwC GenAI API (synchronous).

    Args:
        texts: List of strings to embed
        model: Embedding model name. Defaults to vertex_ai.text-embedding-005
        task_name: Key in llm_config.yml to resolve model
        timeout: Request timeout in seconds

    Returns:
        List of embedding vectors (one per input text)
    """
    _config.validate()

    task_cfg = _resolve_task_config(task_name)
    if task_cfg:
        model = model or task_cfg.model
        timeout = timeout if timeout is not None else task_cfg.timeout

    resolved_model = model or "vertex_ai.text-embedding-005"
    timeout_value = timeout or _config.default_timeout
    endpoint = _config.get_endpoint(ModelType.EMBEDDING)

    log_debug(
        f"[embedding-sync] task={task_name or 'adhoc'} model={resolved_model} texts={len(texts)}",
        "pwc_llm",
    )

    request_body = _build_embedding_request_body(texts, resolved_model)
    headers = _build_headers()

    span = start_span(
        name=f"embedding-sync/{task_name or 'adhoc'}",
        input=f"texts={len(texts)}, model={resolved_model}, first={texts[0][:200] if texts else ''}",
        metadata={"model": resolved_model, "text_count": len(texts)},
    )

    try:
        response = requests.post(endpoint, json=request_body, headers=headers, timeout=timeout_value)

        if response.status_code != 200:
            raise ValueError(f"PwC GenAI Embedding API Error: {response.status_code} - {response.text}")

        result = response.json()
        embeddings = _extract_embeddings_from_response(result)
        span.end(output=f"Generated {len(embeddings)} embeddings, dims={len(embeddings[0]) if embeddings else 0}")
        langfuse_flush()
        return embeddings
    except Exception as _exc:
        span.end(output=f"ERROR: {_exc}")
        langfuse_flush()
        raise


# ============================================================================
# Audio Transcription
# ============================================================================

async def call_pwc_transcribe_async(
    audio_data: bytes,
    model: Optional[str] = None,
    task_name: Optional[str] = None,
    language: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """
    Transcribe audio to text via PwC GenAI API.

    Args:
        audio_data: Raw audio bytes (wav, mp3, etc.)
        model: Transcription model name. Defaults to openai.whisper
        task_name: Key in llm_config.yml to resolve model
        language: Optional language hint (e.g. "en")
        timeout: Request timeout in seconds

    Returns:
        str: The transcribed text
    """
    _config.validate()

    task_cfg = _resolve_task_config(task_name)
    if task_cfg:
        model = model or task_cfg.model
        timeout = timeout if timeout is not None else task_cfg.timeout

    resolved_model = model or "openai.whisper"
    timeout_value = timeout or _config.default_timeout
    endpoint = _config.get_endpoint(ModelType.AUDIO)

    log_debug(
        f"[transcribe] task={task_name or 'adhoc'} model={resolved_model} "
        f"audio_size={len(audio_data)} bytes",
        "pwc_llm",
    )

    request_body = _build_transcription_request_body(audio_data, resolved_model, language)
    headers = _build_headers()

    span = start_span(
        name=f"transcribe/{task_name or 'adhoc'}",
        input=f"model={resolved_model}, audio_size={len(audio_data)} bytes, language={language or 'auto'}",
        metadata={"model": resolved_model, "audio_size_bytes": len(audio_data), "language": language},
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_value) as client:
            response = await client.post(endpoint, json=request_body, headers=headers)

        if response.status_code != 200:
            raise ValueError(f"PwC GenAI Transcription API Error: {response.status_code} - {response.text}")

        result = response.json()
        text = _extract_transcription_from_response(result)
        span.end(output=text[:8000])
        langfuse_flush()
        return text
    except Exception as _exc:
        span.end(output=f"ERROR: {_exc}")
        langfuse_flush()
        raise


def call_pwc_transcribe_sync(
    audio_data: bytes,
    model: Optional[str] = None,
    task_name: Optional[str] = None,
    language: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """
    Transcribe audio to text via PwC GenAI API (synchronous).

    Args:
        audio_data: Raw audio bytes (wav, mp3, etc.)
        model: Transcription model name. Defaults to openai.whisper
        task_name: Key in llm_config.yml to resolve model
        language: Optional language hint (e.g. "en")
        timeout: Request timeout in seconds

    Returns:
        str: The transcribed text
    """
    _config.validate()

    task_cfg = _resolve_task_config(task_name)
    if task_cfg:
        model = model or task_cfg.model
        timeout = timeout if timeout is not None else task_cfg.timeout

    resolved_model = model or "openai.whisper"
    timeout_value = timeout or _config.default_timeout
    endpoint = _config.get_endpoint(ModelType.AUDIO)

    log_debug(
        f"[transcribe-sync] task={task_name or 'adhoc'} model={resolved_model} "
        f"audio_size={len(audio_data)} bytes",
        "pwc_llm",
    )

    request_body = _build_transcription_request_body(audio_data, resolved_model, language)
    headers = _build_headers()

    span = start_span(
        name=f"transcribe-sync/{task_name or 'adhoc'}",
        input=f"model={resolved_model}, audio_size={len(audio_data)} bytes, language={language or 'auto'}",
        metadata={"model": resolved_model, "audio_size_bytes": len(audio_data), "language": language},
    )

    try:
        response = requests.post(endpoint, json=request_body, headers=headers, timeout=timeout_value)

        if response.status_code != 200:
            raise ValueError(f"PwC GenAI Transcription API Error: {response.status_code} - {response.text}")

        result = response.json()
        text = _extract_transcription_from_response(result)
        span.end(output=text[:8000])
        langfuse_flush()
        return text
    except Exception as _exc:
        span.end(output=f"ERROR: {_exc}")
        langfuse_flush()
        raise


# ============================================================================
# Helpers
# ============================================================================

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


__all__ = [
    'call_pwc_genai_async',
    'call_pwc_genai_sync',
    'call_pwc_embedding_async',
    'call_pwc_embedding_sync',
    'call_pwc_transcribe_async',
    'call_pwc_transcribe_sync',
    'build_pwc_prompt',
    'get_pwc_config',
    'detect_model_type',
    'ModelType',
    'PWCLLMConfig',
]
