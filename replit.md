# Defuse 2.O

## Overview

Defuse 2.O is an AI-powered documentation and business requirements document (BRD) generator. It analyzes GitHub repositories to automatically generate comprehensive technical documentation, BRDs, test cases, and test data using PWC GenAI. The application aims to streamline the software development lifecycle by offering features like AI-powered code generation, JIRA integration for user stories, Confluence publishing, and an integrated knowledge base.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend
The frontend is built with React 18 and TypeScript, using Wouter for routing and TanStack Query for state management. `shadcn/ui` and Radix UI provide the component library, styled with Tailwind CSS supporting light/dark modes. Vite is used for building.

### Backend
The backend is a Python 3.11 FastAPI application. It features RESTful JSON APIs, PWC GenAI integration via `httpx`, and handles file uploads using `python-multipart`. SSE streaming is used for BRD generation. `psycopg2` is used for PostgreSQL introspection and `pymongo` for MongoDB knowledge base operations. The backend follows a layered architecture with dedicated modules for core configuration, API routes, Pydantic schemas, data access (repositories), business logic (services), and AI agent implementations. Large backend modules are split into focused sub-modules for maintainability (e.g., `server_py/agents/unit_test_agent/`, `server_py/agents/jira_agent/`).

### Data Storage
PostgreSQL is the primary data store for all domain entities, accessed via `psycopg2` through a custom repository layer. All domain tables use `project_id` foreign keys for multi-tenancy, and JSONB columns store structured nested data. MongoDB Atlas is used for the knowledge base vector search with per-project scoping via `project_id` field.

### Key Design Patterns
The system employs shared types between client and server, path aliases for organized imports, and a clear separation of concerns. Session data is fully persisted in PostgreSQL, with an in-memory artifact cache that syncs with the database.

### AI Features
Defuse 2.O leverages AI for GitHub repository analysis, BRD generation, test case and test data generation, user story and Copilot prompt generation, and BPMN business flow diagram generation. It includes specialized AI agents for security, unit testing, web testing, and code generation.

### UI/UX Decisions
The application uses a GitHub-inspired color palette, JetBrains Mono for code blocks, and supports dark/light modes. Key components include a multi-step workflow sidebar, syntax-highlighted code blocks, rich document rendering, and visual feedback for AI processing.

### Feature Specifications
- **JIRA Integration**: Supports syncing user stories to JIRA, semantic search for related stories, and dynamic creation of Stories, Bugs, or Tasks.
- **Confluence Integration**: Enables publishing generated BRDs to Confluence in Atlassian Document Format.
- **BPMN Diagrams**: Automatically generates and renders BPMN business flow diagrams using Mermaid.js.
- **Knowledge Base (RAG System)**: Integrates with MongoDB Atlas for a RAG system with per-project data isolation. Supports drag-and-drop document upload (PDF, Word, PowerPoint, TXT, MD, JSON, CSV) with multimodal processing. Images embedded in PDF/Word/PPT documents are automatically extracted (via PyMuPDF for PDF, python-docx for Word, python-pptx for PowerPoint) and captioned using Vision AI (vertex_ai.gemini-2.5-flash-image via PwC GenAI). Image captions are merged into the text stream before chunking, enabling semantic search over both text and visual content. Uses fastembed (BAAI/bge-small-en-v1.5, 384-dim) for vector embeddings. Includes a RAG chat interface for testing queries against uploaded documents with SSE-streamed LLM responses and source citation display. Key modules: `utils/doc_parsing.py` (multimodal parser), `utils/image_captioning.py` (vision LLM captioning), `services/knowledge_base_service.py` (ingestion), `api/v1/knowledge_base.py` (upload + chat endpoints with SSE).
- **External Database Schema Integration**: Connects to external PostgreSQL databases to fetch and store schema details for AI context.
- **Session Management**: All session data is stored in PostgreSQL via `workflow_sessions` and `session_artifacts` tables.
- **Project Management (Multi-Tenancy)**: Supports many-to-many user-project relationships, with access controls based on project assignment.

## External Dependencies

### AI Services
- **PWC GenAI**: Primary AI provider for all text generation tasks.
  - Available models: `vertex_ai.gemini-2.5-flash-image`, `vertex_ai.gemini-2.5-pro`, `azure.gpt-5.2`, `vertex_ai.anthropic.claude-sonnet-4-6`, `azure.grok-4-fast-reasoning`.
  - Model selection is controlled via `server_py/llm_config.yml`.
  - All LLM calls route through `utils/pwc_llm.py`.

### Database
- **PostgreSQL**: Primary transactional database.
- **MongoDB Atlas**: Used for the Knowledge Base and vector search capabilities.

### External APIs
- **GitHub API**: Used for repository analysis (metadata, file trees, contents).

### Key NPM Packages
- **Frontend**: React, TanStack Query, Radix UI, Tailwind CSS, Wouter, date-fns.
- **Build**: Vite, esbuild, TypeScript.

### Python Packages (Backend)
- **Web Framework**: FastAPI, uvicorn, starlette.
- **HTTP Client**: httpx.
- **Validation**: pydantic.
- **File Parsing**: PyPDF2, python-docx, PyMuPDF (fitz), python-pptx.
- **SSE**: sse-starlette.
- **Database Connectors**: psycopg2-binary, pymongo.
- **Utilities**: python-dotenv, aiofiles, python-multipart.