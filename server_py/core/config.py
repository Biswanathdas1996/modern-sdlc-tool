"""Application configuration settings."""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "DocuGen AI API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 5000
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    # AI/GenAI
    pwc_genai_endpoint_url: str = ""
    pwc_genai_api_key: str = ""
    pwc_genai_bearer_token: str = ""
    
    # GitHub
    github_personal_access_token: Optional[str] = None
    
    # JIRA
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_instance_url: str = "daspapun21.atlassian.net"
    jira_project_key: str = "KAN"
    
    # Confluence
    confluence_space_key: str = "~5caf6d452c573b4b24d0f933"
    
    # MongoDB
    mongodb_uri: Optional[str] = None
    mongodb_db_name: str = "docugen_knowledge"
    
    # Vite Dev Server
    vite_dev_server: str = "http://localhost:5173"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        return cls(
            pwc_genai_endpoint_url=os.getenv("PWC_GENAI_ENDPOINT_URL", ""),
            pwc_genai_api_key=os.getenv("PWC_GENAI_API_KEY", ""),
            pwc_genai_bearer_token=os.getenv("PWC_GENAI_BEARER_TOKEN", ""),
            github_personal_access_token=os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
            jira_email=os.getenv("JIRA_EMAIL"),
            jira_api_token=os.getenv("JIRA_API_TOKEN"),
            jira_instance_url=os.getenv("JIRA_INSTANCE_URL", "daspapun21.atlassian.net"),
            jira_project_key=os.getenv("JIRA_PROJECT_KEY", "KAN"),
            confluence_space_key=os.getenv("CONFLUENCE_SPACE_KEY", "~5caf6d452c573b4b24d0f933"),
            mongodb_uri=os.getenv("MONGODB_URI"),
            mongodb_db_name=os.getenv("MONGODB_DB_NAME", "docugen_knowledge"),
            environment=os.getenv("NODE_ENV", "development"),
            port=int(os.getenv("PORT", "5000")),
            vite_dev_server=os.getenv("VITE_DEV_SERVER", "http://localhost:5173"),
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_env()
