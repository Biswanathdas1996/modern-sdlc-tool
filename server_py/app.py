"""Modern FastAPI application entry point."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (parent of server_py directory)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

# Import configurations and middleware
from core.config import get_settings
from core.logging import setup_logging
from core.database import mongo_db
from middleware.logging import LoggingMiddleware

# Import API routers
from api.v1 import (
    auth,
    projects,
    knowledge_base,
    jira,
    jira_agent,
    agents,
    documentation,
    database_schema,
    requirements,
    confluence
)

# Setup logging
setup_logging()
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered documentation and requirements generation"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Include API routers
app.include_router(auth.router, prefix="/api")              # Auth & admin endpoints
app.include_router(projects.router, prefix="/api")          # Project management
app.include_router(knowledge_base.router, prefix="/api")    # Knowledge base
app.include_router(jira.router, prefix="/api")              # JIRA integration
app.include_router(jira_agent.router, prefix="/api")        # JIRA AI agent
app.include_router(agents.router, prefix="/api")            # AI agents (security, unit-test, web-test, code-gen)
app.include_router(documentation.router, prefix="/api")     # Repository analysis & BPMN
app.include_router(database_schema.router, prefix="/api")   # PostgreSQL schema extraction
app.include_router(requirements.router, prefix="/api")      # BRD, test cases, user stories
app.include_router(confluence.router, prefix="/api")        # Confluence publishing


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    from core.logging import log_info, log_error
    
    log_info(f"{settings.app_name} v{settings.app_version} starting", "app")
    log_info(f"Environment: {settings.environment}", "app")
    log_info(f"Server: http://{settings.host}:{settings.port}", "app")
    
    # Connect to MongoDB if configured
    if settings.mongodb_uri:
        try:
            mongo_db.connect()
            log_info("MongoDB connected successfully", "app")
        except Exception as e:
            log_error("MongoDB connection failed", "app", e)
    else:
        log_info("MongoDB not configured (MONGODB_URI not set)", "app")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    from core.logging import log_info
    log_info("Application shutting down", "app")
    mongo_db.disconnect()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.app_version}


# Vite dev server proxy (for development)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_to_vite(request: Request, path: str):
    """Proxy requests to Vite dev server or serve static files."""
    # Skip API routes
    if path.startswith("api/"):
        return JSONResponse(
            status_code=404,
            content={"detail": "API endpoint not found"}
        )
    
    # Production: serve static files
    if settings.environment == "production":
        try:
            static_path = (
                f"../client/dist/{path}" if path else "../client/dist/index.html"
            )
            if os.path.exists(static_path):
                with open(static_path, "rb") as f:
                    content = f.read()
                
                # Determine content type
                content_type = "text/html"
                if path.endswith(".js"):
                    content_type = "application/javascript"
                elif path.endswith(".css"):
                    content_type = "text/css"
                elif path.endswith(".json"):
                    content_type = "application/json"
                
                return Response(content=content, media_type=content_type)
            else:
                # Serve index.html for SPA routes
                with open("../client/dist/index.html", "rb") as f:
                    content = f.read()
                return Response(content=content, media_type="text/html")
        except Exception:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
    
    # Development: proxy to Vite dev server
    else:
        try:
            async with httpx.AsyncClient() as client:
                url = f"{settings.vite_dev_server}/{path}"
                if request.query_params:
                    url += f"?{request.query_params}"
                
                response = await client.request(
                    method=request.method,
                    url=url,
                    headers={
                        k: v for k, v in request.headers.items()
                        if k.lower() not in ["host", "content-length"]
                    },
                    content=await request.body() 
                        if request.method in ["POST", "PUT", "PATCH"] 
                        else None,
                    timeout=30.0
                )
                
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers={
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ["transfer-encoding", "content-encoding"]
                    }
                )
        except Exception as e:
            return Response(
                content=f"""<!DOCTYPE html>
<html>
<body>
    <h1>Vite Dev Server Not Running</h1>
    <p>Please start Vite: npm run dev:client</p>
    <p>Error: {e}</p>
</body>
</html>""",
                media_type="text/html"
            )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info"
    )
