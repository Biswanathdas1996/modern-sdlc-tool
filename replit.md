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
- **server_py/agents/jira_agent/**: Agentic architecture with `jira_agent.py` (slim orchestrator, ~139 lines), `direct_processor.py` (routing dispatcher, ~98 lines), `tools/` (13 capability modules: existing JIRA operations + 7 new processors: process_create, process_update, process_search, process_subtask, process_link, process_issue_report, process_info_response, legacy_processor, enrich_context), `utils/` (3 pure utilities: action_types, intent_analyzer, error_handler), `helpers/` (3 domain helpers: validators, extractors, messages). Backward compatibility via shim re-exports in old files.
- **server_py/agents/shannon_security_agent/**: `security_analyzers.py`, `assessment.py`, `agent.py` (coordinator)
- **server_py/services/**: `github_fetcher.py`, `generators.py`, `ai_service.py` (core + delegation wrappers)
- Pattern: Coordinator/orchestrator classes import standalone functions from sub-modules. Backward compatibility maintained via class delegation methods and `__init__.py` exports.

### Data Storage
PostgreSQL is the primary data store for all domain entities, accessed via `psycopg2` through a custom repository layer (`server_py/repositories/pg_repository.py`). All domain tables (projects, repo_analyses, documentation, bpmn_diagrams, feature_requests, brds, test_cases, test_data, user_stories, database_schemas, knowledge_documents) use `project_id` foreign keys for multi-tenancy. JSONB columns store structured nested data (tech stacks, BRD content, test steps, etc.). The `StorageManager` (`server_py/repositories/storage.py`) provides a unified API returning plain Python dicts with camelCase keys. Schema initialization runs at startup via `init_postgres_database()`. Frontend uses Zod schemas in `shared/schema.ts` for type validation. MongoDB Atlas remains for the knowledge base vector search with per-project scoping via `project_id` field.

### Key Design Patterns
The system employs shared types between client and server, path aliases for organized imports, and a clear separation of concerns with routes, services, and repositories. Session data is fully persisted in PostgreSQL (no localStorage except theme). The `useSession` hook provides an in-memory artifact cache that syncs with the database-backed `session_artifacts` table via REST API calls.

### AI Features
Defuse 2.O leverages AI for GitHub repository analysis, BRD generation, test case and test data generation, user story and Copilot prompt generation, and BPMN business flow diagram generation. It includes specialized AI agents for security, unit testing, web testing, and code generation.

### UI/UX Decisions
The application uses a GitHub-inspired color palette, JetBrains Mono for code blocks, and supports dark/light modes. Key components include a multi-step workflow sidebar, syntax-highlighted code blocks, rich document rendering, and visual feedback for AI processing.

### Feature Specifications
- **JIRA Integration**: Supports syncing user stories to JIRA, semantic search for related stories, and dynamic creation of Stories, Bugs, or Tasks based on request type. Allows editing stories before syncing and creating subtasks.
- **Confluence Integration**: Enables publishing generated BRDs to Confluence in Atlassian Document Format.
- **BPMN Diagrams**: Automatically generates and renders comprehensive BPMN business flow diagrams using Mermaid.js.
- **Knowledge Base (RAG System)**: Integrates with MongoDB Atlas for a RAG system with per-project data isolation. Each project gets its own MongoDB collections (`knowledge_chunks_{project_id}` and `knowledge_documents_{project_id}`) with dedicated indexes (`text_search_index`, `documentId_1`, `id_1`). Supports drag-and-drop document upload (TXT, MD, JSON, CSV), automatic text chunking, and keyword-based search during BRD and user story generation. All KB operations (upload, search, list, delete, stats) require a `project_id` parameter.
- **External Database Schema Integration**: Users can connect to external PostgreSQL databases to fetch and store schema details, which are then used as context for AI prompts.
- **Session Management**: All session data is stored in PostgreSQL via `workflow_sessions` and `session_artifacts` tables. No localStorage is used except for theme. Frontend `useSession` hook fetches active session and artifacts from `/api/sessions/active` API, caches artifacts in-memory, and persists changes via API calls. Artifact types include: project, documentation, analysis, featureRequest, brd, userStories, testCases, testData, bpmn, databaseSchema, copilotPrompt.
- **Project Management (Multi-Tenancy)**: Many-to-many user-project relationships via `user_projects` junction table. Users can belong to multiple projects. Admins see all projects; non-admin users see only their assigned projects via `/api/user-projects` endpoint. Frontend uses `useProject()` context hook for project-scoped data access. The `useAuth` hook provides both `projectId` (legacy single) and `projectIds` (array) fields.

## External Dependencies

### AI Services
- **PWC GenAI**: Primary AI provider for all text generation tasks.
  - Available models: `vertex_ai.gemini-2.0-flash`, `vertex_ai.gemini-2.0-flash-001`, `azure.gpt-4o`, `vertex_ai.anthropic.claude-sonnet-4`, `bedrock.anthropic.claude-sonnet-4`
  - Model selection controlled via `server_py/llm_config.yml` (26 task-specific entries)
  - Config loader: `server_py/core/llm_config.py` → `get_llm_config().get(task_name)`
  - All LLM calls route through `utils/pwc_llm.py` which resolves model from YAML config via `task_name` parameter

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