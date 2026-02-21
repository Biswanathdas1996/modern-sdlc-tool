"""Shared Langfuse observability module for the entire application.

Every LLM call made through ``call_pwc_genai_async`` / ``call_pwc_genai_sync``
automatically creates a Langfuse *generation* span — no per-feature wiring needed.

The JIRA agent additionally creates *traces* (via ``create_trace``) so its
multi-step flows appear as a single top-level trace with child generations.

All helpers silently no-op when:
- ``LANGFUSE_ENABLED=false`` in .env
- Keys are missing
- The ``langfuse`` package is not installed
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.logging import log_info, log_warning, log_error

# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------
_langfuse_client = None
_langfuse_handler = None   # LangChain callback handler
_initialised = False


def _init() -> bool:
    """Initialise Langfuse once. Returns True when ready."""
    global _langfuse_client, _langfuse_handler, _initialised

    if _initialised:
        return _langfuse_client is not None

    _initialised = True

    from core.config import get_settings
    settings = get_settings()

    if not settings.langfuse_enabled:
        log_info("Langfuse disabled (LANGFUSE_ENABLED=false)", "langfuse")
        return False

    if not settings.langfuse_secret_key or not settings.langfuse_public_key:
        log_warning(
            "Langfuse keys not set — tracing disabled. "
            "Add LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY to .env",
            "langfuse",
        )
        return False

    try:
        from langfuse import Langfuse
        from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

        _langfuse_client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_base_url,
        )
        _langfuse_client.auth_check()
        log_info(f"Langfuse ready → {settings.langfuse_base_url}", "langfuse")

        _langfuse_handler = LangfuseCallbackHandler(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_base_url,
        )
        return True

    except ImportError:
        log_warning("langfuse package not installed — pip install langfuse", "langfuse")
        return False
    except Exception as exc:
        log_error(f"Langfuse init failed: {exc}", "langfuse")
        return False


# ---------------------------------------------------------------------------
# LangChain callback handler (for agent-based flows)
# ---------------------------------------------------------------------------

def get_langfuse_handler(**kwargs) -> Optional[Any]:
    """Return a fresh per-request LangChain CallbackHandler.

    Pass optional kwargs to set trace metadata::

        handler = get_langfuse_handler(
            trace_name="jira-agent-chat",
            session_id=session_id,
            tags=["jira-agent"],
        )
    """
    if not _init():
        return None

    try:
        from core.config import get_settings
        from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

        settings = get_settings()
        return LangfuseCallbackHandler(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_base_url,
            trace_name=kwargs.get("trace_name", "pwc-llm"),
            session_id=kwargs.get("session_id"),
            user_id=kwargs.get("user_id"),
            tags=kwargs.get("tags", ["pwc-llm"]),
            metadata=kwargs.get("metadata"),
        )
    except Exception as exc:
        log_warning(f"Could not create Langfuse handler: {exc}", "langfuse")
        return None


# ---------------------------------------------------------------------------
# Manual trace helper (for direct-processing flows)
# ---------------------------------------------------------------------------

def get_langfuse_client() -> Optional[Any]:
    """Return the shared Langfuse client for manual span creation."""
    _init()
    return _langfuse_client


def create_trace(
    name: str,
    input: Optional[Any] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Optional[Any]:
    """Create a top-level Langfuse trace. Returns the trace object or None.

    Args:
        name: Trace name (e.g. "jira-agent-interactive")
        input: The user's input/query that triggered this trace
        session_id: Session identifier for grouping traces
        user_id: User identifier
        metadata: Additional key-value metadata
        tags: List of tags for filtering in Langfuse UI
    """
    client = get_langfuse_client()
    if client is None:
        return None

    try:
        kwargs: Dict[str, Any] = dict(
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata or {},
            tags=tags or [],
        )
        if input is not None:
            kwargs["input"] = input if isinstance(input, str) and len(input) <= 8000 else str(input)[:8000]
        return client.trace(**kwargs)
    except Exception as exc:
        log_warning(f"Failed to create Langfuse trace: {exc}", "langfuse")
        return None


# ---------------------------------------------------------------------------
# Generation tracing — called directly from pwc_llm.py
# ---------------------------------------------------------------------------

class _NoopGeneration:
    """Sentinel returned when Langfuse is off so callers need no if-guard."""
    def end(self, **_kwargs):
        pass

    def update(self, **_kwargs):
        pass


def start_generation(
    *,
    task_name: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    """Open a Langfuse generation span.

    Returns a generation object with an ``.end(output=..., usage=...)`` method,
    or a no-op sentinel when Langfuse is unavailable.

    Usage::

        gen = start_generation(task_name="brd_generation", model=..., ...)
        try:
            response = await http_call(...)
            gen.end(output=response, usage={"input": 100, "output": 50})
        except Exception:
            gen.end(output="ERROR", level="ERROR")
            raise
    """
    client = get_langfuse_client()
    if client is None:
        return _NoopGeneration()

    try:
        kwargs: Dict[str, Any] = dict(
            name=f"llm/{task_name}",
            model=model,
            model_parameters={
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            input=prompt[:8000],
            metadata=metadata or {},
        )
        if trace_id:
            kwargs["trace_id"] = trace_id

        return client.generation(**kwargs)
    except Exception as exc:
        log_warning(f"Failed to start Langfuse generation: {exc}", "langfuse")
        return _NoopGeneration()


# ---------------------------------------------------------------------------
# Span tracing — for non-generation operations (embeddings, transcriptions)
# ---------------------------------------------------------------------------

class _NoopSpan:
    """Sentinel returned when Langfuse is off so callers need no if-guard."""
    def end(self, **_kwargs):
        pass

    def update(self, **_kwargs):
        pass


def start_span(
    *,
    name: str,
    input: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> Any:
    """Open a Langfuse span for non-generation operations.

    Use this for embedding calls, transcription calls, or any operation
    that isn't a text-generation LLM call.

    Returns a span object with ``.end(output=...)`` or a no-op sentinel.
    """
    client = get_langfuse_client()
    if client is None:
        return _NoopSpan()

    try:
        kwargs: Dict[str, Any] = dict(
            name=name,
            metadata=metadata or {},
        )
        if input is not None:
            input_str = str(input) if not isinstance(input, str) else input
            kwargs["input"] = input_str[:8000]
        if trace_id:
            kwargs["trace_id"] = trace_id

        return client.span(**kwargs)
    except Exception as exc:
        log_warning(f"Failed to start Langfuse span: {exc}", "langfuse")
        return _NoopSpan()


# ---------------------------------------------------------------------------
# Usage extraction helper
# ---------------------------------------------------------------------------

def extract_usage(api_response: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """Extract token usage from a PwC GenAI API response.

    Returns a dict like {"input": 100, "output": 50, "total": 150}
    or None if usage data is not present in the response.
    """
    usage = api_response.get("usage")
    if not usage:
        return None

    result: Dict[str, int] = {}
    if "prompt_tokens" in usage:
        result["input"] = usage["prompt_tokens"]
    elif "input_tokens" in usage:
        result["input"] = usage["input_tokens"]

    if "completion_tokens" in usage:
        result["output"] = usage["completion_tokens"]
    elif "output_tokens" in usage:
        result["output"] = usage["output_tokens"]

    if "total_tokens" in usage:
        result["total"] = usage["total_tokens"]
    elif "input" in result and "output" in result:
        result["total"] = result["input"] + result["output"]

    return result if result else None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def flush() -> None:
    """Flush buffered Langfuse events. Call before shutdown."""
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception:
            pass


def shutdown() -> None:
    """Gracefully shut down the Langfuse client."""
    global _langfuse_client, _langfuse_handler, _initialised
    flush()
    if _langfuse_client is not None:
        try:
            _langfuse_client.shutdown()
        except Exception:
            pass
    _langfuse_client = None
    _langfuse_handler = None
    _initialised = False
