"""Logging middleware for HTTP requests."""
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from core.logging import log_request


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests and responses."""
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response."""
        start_time = datetime.now()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        # Log only API requests
        if request.url.path.startswith("/api"):
            log_request(
                request.method,
                request.url.path,
                response.status_code,
                duration
            )
        
        return response
