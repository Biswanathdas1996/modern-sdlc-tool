"""Backward-compatible re-export of the shared core.langfuse module.

All JIRA-agent code that previously imported from this module continues to
work unchanged. New code should import from ``core.langfuse`` directly.
"""
from core.langfuse import (
    get_langfuse_handler,
    get_langfuse_client,
    create_trace,
    start_generation,
    flush,
    shutdown,
)

__all__ = [
    "get_langfuse_handler",
    "get_langfuse_client",
    "create_trace",
    "start_generation",
    "flush",
    "shutdown",
]
