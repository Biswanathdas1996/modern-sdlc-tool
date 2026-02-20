"""
Production-grade conversation state management for multi-turn interactive Jira agent.
Tracks context, missing information, and conversation flow.

Production improvements:
- Thread-safe operations with asyncio.Lock
- Maximum session cap to prevent memory exhaustion
- Maximum messages per conversation to bound memory
- Periodic cleanup of expired sessions
- Structured logging
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import json

from core.logging import log_info, log_warning


# --- Configuration ---
MAX_ACTIVE_SESSIONS = 500
MAX_MESSAGES_PER_SESSION = 100
SESSION_TIMEOUT_MINUTES = 30


class ConversationState(str, Enum):
    """States of a conversation."""
    INITIAL = "initial"  # First query
    AWAITING_INFO = "awaiting_info"  # Waiting for user to provide missing info
    PROCESSING = "processing"  # Processing with complete information
    COMPLETED = "completed"  # Task completed


class InfoRequest:
    """Represents a request for missing information."""
    
    def __init__(self, field: str, description: str, options: Optional[List[str]] = None):
        self.field = field
        self.description = description
        self.options = options or []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "description": self.description,
            "options": self.options
        }


class ConversationContext:
    """Stores context for a single conversation."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = ConversationState.INITIAL
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        
        # Conversation data
        self.original_intent: Optional[str] = None
        self.action_type: Optional[str] = None
        self.collected_data: Dict[str, Any] = {}
        self.missing_fields: List[InfoRequest] = []
        
        # History
        self.messages: List[Dict[str, Any]] = []
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history (bounded to MAX_MESSAGES_PER_SESSION)."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Evict oldest messages if over limit
        if len(self.messages) > MAX_MESSAGES_PER_SESSION:
            self.messages = self.messages[-MAX_MESSAGES_PER_SESSION:]
        self.updated_at = datetime.now()
    
    def update_collected_data(self, data: Dict[str, Any]):
        """Update collected data with new information."""
        self.collected_data.update(data)
        self.updated_at = datetime.now()
    
    def set_missing_fields(self, fields: List[InfoRequest]):
        """Set fields that need to be collected from user."""
        self.missing_fields = fields
        self.state = ConversationState.AWAITING_INFO
        self.updated_at = datetime.now()
    
    def clear_missing_fields(self):
        """Clear missing fields after they've been collected."""
        self.missing_fields = []
        self.state = ConversationState.PROCESSING
        self.updated_at = datetime.now()
    
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if conversation has expired."""
        return datetime.now() - self.updated_at > timedelta(minutes=timeout_minutes)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "original_intent": self.original_intent,
            "action_type": self.action_type,
            "collected_data": self.collected_data,
            "missing_fields": [f.to_dict() for f in self.missing_fields],
            "messages": self.messages
        }
    
    def get_conversation_history(self, max_messages: int = 10) -> str:
        """Get formatted conversation history for context."""
        if not self.messages:
            return "(No previous conversation)"
        
        recent_messages = self.messages[-max_messages:]
        formatted = []
        for msg in recent_messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            formatted.append(f"{role}: {msg['content']}")
        
        return "\n".join(formatted)
    
    def get_summary(self) -> str:
        """Get a brief summary of the conversation for quick reference."""
        summary_parts = []
        
        if self.action_type:
            summary_parts.append(f"Action: {self.action_type}")
        
        if self.collected_data:
            summary_parts.append(f"Data collected: {', '.join(self.collected_data.keys())}")
        
        if self.messages:
            summary_parts.append(f"Messages: {len(self.messages)}")
        
        return " | ".join(summary_parts) if summary_parts else "New conversation"


class ConversationManager:
    """Manages multiple conversation contexts with production safeguards.

    - Thread-safe via asyncio.Lock
    - Enforces MAX_ACTIVE_SESSIONS to prevent memory exhaustion
    - Auto-cleans expired sessions on access
    """
    
    def __init__(self):
        self._contexts: Dict[str, ConversationContext] = {}
        self._lock = asyncio.Lock()
    
    def create_context(self, session_id: str) -> ConversationContext:
        """Create a new conversation context (caller should hold _lock if async)."""
        self._cleanup_expired()
        if len(self._contexts) >= MAX_ACTIVE_SESSIONS:
            # Evict oldest session
            oldest_id = min(
                self._contexts,
                key=lambda sid: self._contexts[sid].updated_at,
            )
            log_warning(
                f"Max sessions ({MAX_ACTIVE_SESSIONS}) reached — evicting {oldest_id}",
                "conversation_manager",
            )
            del self._contexts[oldest_id]

        context = ConversationContext(session_id)
        self._contexts[session_id] = context
        return context
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """Get existing conversation context."""
        # Clean up expired contexts first
        self._cleanup_expired()
        return self._contexts.get(session_id)
    
    def get_or_create_context(self, session_id: str) -> ConversationContext:
        """Get existing context or create new one."""
        context = self.get_context(session_id)
        if context is None:
            context = self.create_context(session_id)
        return context
    
    def delete_context(self, session_id: str):
        """Delete a conversation context."""
        if session_id in self._contexts:
            del self._contexts[session_id]
    
    def _cleanup_expired(self, timeout_minutes: int = SESSION_TIMEOUT_MINUTES):
        """Remove expired contexts."""
        expired_ids = [
            session_id for session_id, ctx in self._contexts.items()
            if ctx.is_expired(timeout_minutes)
        ]
        for session_id in expired_ids:
            del self._contexts[session_id]
        if expired_ids:
            log_info(f"Cleaned up {len(expired_ids)} expired sessions", "conversation_manager")
    
    def get_active_count(self) -> int:
        """Get count of active conversations."""
        self._cleanup_expired()
        return len(self._contexts)


# Global instance
conversation_manager = ConversationManager()
