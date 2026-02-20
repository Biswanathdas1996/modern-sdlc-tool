"""Langfuse LLM observability integration for JIRA agent.

Provides:
- LangChain callback handler for automatic tracing of agent runs
- Trace/span helpers for custom instrumentation of direct processing
- Graceful no-op fallback when Langfuse is unavailable or disabled

All traces land in the Langfuse dashboard under the "jira-agent" project tag,
giving full visibility into LLM calls, tool usage, latency, and token costs.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.logging import log_info, log_warning, log_error

# ---------------------------------------------------------------------------
# Lazy-initialised Langfuse client & callback handler
# ---------------------------------------------------------------------------
_langfuse_client = None
_langfuse_handler = None
_initialised = False


def _init_langfuse() -> bool:
    """Initialise the Langfuse client singleton. Returns True on success."""
    global _langfuse_client, _langfuse_handler, _initialised

    if _initialised:
        return _langfuse_client is not None

    _initialised = True
    settings = get_settings()

    if not settings.langfuse_enabled:
        log_info("Langfuse tracing is disabled via LANGFUSE_ENABLED=false", "langfuse")
        return False

    if not settings.langfuse_secret_key or not settings.langfuse_public_key:
        log_warning(
            "Langfuse keys not configured — tracing disabled. "
            "Set LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY in .env",
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

        # Verify connectivity (non-blocking best-effort)
        _langfuse_client.auth_check()
        log_info(
            f"Langfuse tracing initialised → {settings.langfuse_base_url}",
            "langfuse",
        )

        _langfuse_handler = LangfuseCallbackHandler(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_base_url,
        )
        return True

    except ImportError:
        log_warning("langfuse package not installed — run: pip install langfuse", "langfuse")
        return False
    except Exception as exc:
        log_error(f"Failed to initialise Langfuse: {exc}", "langfuse")
        return False


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_langfuse_handler(**kwargs) -> Optional[Any]:
    """Return a *fresh* LangChain CallbackHandler for each request.

    Each call creates a new handler instance so that every agent invocation
    gets its own trace in Langfuse.  Pass optional ``kwargs`` to override
    trace metadata:

        handler = get_langfuse_handler(
            trace_name="jira-agent-chat",
            session_id=session_id,
            user_id=user_id,
            tags=["interactive"],
            metadata={"intent": "create"},
        )

    Returns ``None`` when Langfuse is disabled/unavailable so callers can
    simply filter it out of the callbacks list.
    """
    if not _init_langfuse():
        return None

    try:
        from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

        settings = get_settings()
        handler = LangfuseCallbackHandler(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_base_url,
            trace_name=kwargs.get("trace_name", "jira-agent"),
            session_id=kwargs.get("session_id"),
            user_id=kwargs.get("user_id"),
            tags=kwargs.get("tags", ["jira-agent"]),
            metadata=kwargs.get("metadata"),
        )
        return handler
    except Exception as exc:
        log_warning(f"Could not create Langfuse handler: {exc}", "langfuse")
        return None


def get_langfuse_client() -> Optional[Any]:
    """Return the shared Langfuse client for manual span/generation creation.

    Useful for tracing *direct processing* code paths that don't go through
    the LangChain agent executor.

    Returns ``None`` when Langfuse is unavailable.
    """
    _init_langfuse()
    return _langfuse_client


def create_trace(
    name: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Optional[Any]:
    """Create a Langfuse trace for manual instrumentation.

    Returns a ``langfuse.client.StatefulTraceClient`` or ``None``.
    """
    client = get_langfuse_client()
    if client is None:
        return None

    try:
        return client.trace(
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata or {},
            tags=tags or ["jira-agent"],
        )
    except Exception as exc:
        log_warning(f"Failed to create Langfuse trace: {exc}", "langfuse")
        return None


def flush() -> None:
    """Flush any buffered Langfuse events (call on shutdown)."""
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
