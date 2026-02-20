# Defuse 2.O

## Overview

Defuse 2.O is an AI-powered documentation and business requirements document (BRD) generator. It analyzes GitHub repositories to automatically generate comprehensive technical documentation, BRDs, test cases, and test data using PWC GenAI. The application streamlines the software development lifecycle by offering features like AI-powered code generation, JIRA integration for user stories, Confluence publishing, and an integrated knowledge base.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend
The frontend is built with React 18 and TypeScript, utilizing Wouter for routing and TanStack Query for state management. shadcn/ui and Radix UI provide the component library, styled with Tailwind CSS supporting light/dark modes. Vite is used for building.

### Backend
The backend is a Python 3.11 FastAPI application. It features RESTful JSON APIs, PWC GenAI integration via `httpx`, and handles file uploads using `python-multipart`. SSE streaming is used for BRD generation. `psycopg2` is used for PostgreSQL introspection and `pymongo` for MongoDB knowledge base operations. The backend follows a layered architecture with dedicated modules for core configuration, API routes, Pydantic schemas, data access (repositories), business logic (services), and AI agent implementations.

### Backend Module Structure (Refactored)
Large backend modules have been split into focused sub-modules for maintainability:
- **server_py/agents/unit_test_agent/**: Agentic architecture with `agent.py` (slim orchestrator, ~365 lines), `tools/` (10 capability modules: analyze_repo, collect_sources, discover_tests, coverage_mapper, generate_tests, fix_tests, run_tests, write_files, validate_and_fix, task_reporter), `utils/` (3 pure utilities: error_classifier, import_resolver, pattern_matcher), `helpers/` (4 domain helpers: deps_context, mocking_guide, npm_runner, test_path). One-way dependency: tools → helpers/utils only.
- **server_py/agents/jira_agent/**: `ticket_actions.py`, `issue_actions.py`, `direct_processor.py` (orchestrator)
- **server_py/agents/shannon_security_agent/**: `security_analyzers.py`, `assessment.py`, `agent.py` (coordinator)
- **server_py/services/**: `github_fetcher.py`, `generators.py`, `ai_service.py` (core + delegation wrappers)
- Pattern: Coordinator/orchestrator classes import standalone functions from sub-modules. Backward compatibility maintained via class delegation methods and `__init__.py` exports.

### Data Storage
Drizzle ORM with a PostgreSQL dialect is used for database interactions, with Zod schemas for validation. The application manages data for projects, repository analysis, documentation, feature requests, BRDs, test cases, and test data. In-memory storage is used via a `StorageManager` and `BaseRepository` pattern.

### Key Design Patterns
The system employs shared types between client and server, path aliases for organized imports, and a clear separation of concerns with routes, services, and repositories. A session restoration mechanism allows the client to send cached session data to the backend, ensuring continuity even after server restarts.

### AI Features
Defuse 2.O leverages AI for GitHub repository analysis, BRD generation, test case and test data generation, user story and Copilot prompt generation, and BPMN business flow diagram generation. It includes specialized AI agents for security, unit testing, web testing, and code generation.

### UI/UX Decisions
The application uses a GitHub-inspired color palette, JetBrains Mono for code blocks, and supports dark/light modes. Key components include a multi-step workflow sidebar, syntax-highlighted code blocks, rich document rendering, and visual feedback for AI processing.

### Feature Specifications
- **JIRA Integration**: Supports syncing user stories to JIRA, semantic search for related stories, and dynamic creation of Stories, Bugs, or Tasks based on request type. Allows editing stories before syncing and creating subtasks.
- **Confluence Integration**: Enables publishing generated BRDs to Confluence in Atlassian Document Format.
- **BPMN Diagrams**: Automatically generates and renders comprehensive BPMN business flow diagrams using Mermaid.js.
- **Knowledge Base (RAG System)**: Integrates with MongoDB Atlas for a RAG system. Supports drag-and-drop document upload (TXT, MD, JSON, CSV), automatic text chunking, and vector embeddings (OpenAI `text-embedding-3-small`) for semantic search during BRD and user story generation.
- **External Database Schema Integration**: Users can connect to external PostgreSQL databases to fetch and store schema details, which are then used as context for AI prompts.
- **Session Management**: Each workflow run generates a unique session ID, persisting all generated artifacts across the client and allowing backend restoration of session data.

## External Dependencies

### AI Services
- **PWC GenAI**: Primary AI provider for all text generation tasks.
  - Model: `vertex_ai.gemini-2.0-flash` (text generation only).

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
- **File Parsing**: PyPDF2, python-docx.
- **SSE**: sse-starlette.
- **Database Connectors**: psycopg2-binary, pymongo.
- **Utilities**: python-dotenv, aiofiles, python-multipart.