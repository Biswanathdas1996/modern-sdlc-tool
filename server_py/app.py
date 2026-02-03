"""Modern FastAPI application entry point."""
import os
from dotenv import load_dotenv
load_dotenv()

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
from api.v1 import projects, knowledge_base

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
app.include_router(projects.router, prefix="/api")
app.include_router(knowledge_base.router, prefix="/api")

# TODO: Add remaining routers
# from api.v1 import brd, test_cases, user_stories, jira
# app.include_router(brd.router, prefix="/api")
# app.include_router(test_cases.router, prefix="/api")
# app.include_router(user_stories.router, prefix="/api")
# app.include_router(jira.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    print(f"\n🚀 {settings.app_name} v{settings.app_version}")
    print(f"📝 Environment: {settings.environment}")
    print(f"🌐 Server: http://{settings.host}:{settings.port}")
    
    # Connect to MongoDB if configured
    if settings.mongodb_uri:
        try:
            mongo_db.connect()
        except Exception as e:
            print(f"⚠️  MongoDB connection failed: {e}")
    else:
        print("⚠️  MongoDB not configured (MONGODB_URI not set)")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    print("\n👋 Shutting down...")
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
