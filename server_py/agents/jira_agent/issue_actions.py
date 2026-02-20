"""Backward-compatible re-exports from tools/ processor modules."""
from .tools.process_issue_report import process_issue_report as _process_issue_report
from .tools.process_info_response import handle_info_response as _handle_info_response
from .tools.legacy_processor import process_without_conversation as _process_without_conversation

__all__ = [
    "_process_issue_report",
    "_handle_info_response",
    "_process_without_conversation",
]
