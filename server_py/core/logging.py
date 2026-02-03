"""Logging configuration."""
import logging
import sys
from datetime import datetime
from typing import Optional


def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
    """Setup application logging."""
    logger = logging.getLogger("docugen")
    logger.setLevel(level)
    
    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%I:%M:%S %p'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    return logger


def log_request(method: str, path: str, status_code: int, duration_ms: float):
    """Log HTTP request."""
    logger = logging.getLogger("docugen")
    logger.info(f"{method} {path} {status_code} in {duration_ms:.0f}ms")


def log_info(message: str, source: str = "app"):
    """Log info message."""
    logger = logging.getLogger("docugen")
    logger.info(f"[{source}] {message}")


def log_error(message: str, source: str = "app", exc: Optional[Exception] = None):
    """Log error message."""
    logger = logging.getLogger("docugen")
    if exc:
        logger.error(f"[{source}] {message}: {str(exc)}", exc_info=True)
    else:
        logger.error(f"[{source}] {message}")


def log_warning(message: str, source: str = "app"):
    """Log warning message."""
    logger = logging.getLogger("docugen")
    logger.warning(f"[{source}] {message}")


def log_debug(message: str, source: str = "app"):
    """Log debug message."""
    logger = logging.getLogger("docugen")
    logger.debug(f"[{source}] {message}")
