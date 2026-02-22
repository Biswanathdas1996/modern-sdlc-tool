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
- **Knowledge Base (RAG System)**: Integrates with MongoDB Atlas for a RAG system with per-project data isolation. Each project gets its own MongoDB collections (`knowledge_chunks_{project_id}` and `knowledge_documents_{project_id}`) with dedicated indexes (`text_search_index`, `documentId_1`, `id_1`). Supports drag-and-drop document upload (TXT, MD, JSON, CSV), section-aware text chunking (500-char chunks with 100-char overlap, breaking at headings/paragraphs/sentences), and vector similarity search using fastembed (BAAI/bge-small-en-v1.5, 384-dim) with keyword fallback during BRD and user story generation. Each chunk stores an `embedding` field (384-dim float array), `embeddingModel`, and `embeddingDimension` in MongoDB. Search uses cosine similarity against stored embeddings via `utils/embeddings.py`. Re-ingestion API (`/reingest/{id}`, `/reingest-all`) allows updating existing documents with improved chunking and embeddings. All KB operations (upload, search, list, delete, stats, reingest) require a `project_id` parameter.
- **External Database Schema Integration**: Users can connect to external PostgreSQL databases to fetch and store schema details, which are then used as context for AI prompts.
- **Session Management**: All session data is stored in PostgreSQL via `workflow_sessions` and `session_artifacts` tables. No localStorage is used except for theme. Frontend `useSession` hook fetches active session and artifacts from `/api/sessions/active` API, caches artifacts in-memory, and persists changes via API calls. Artifact types include: project, documentation, analysis, featureRequest, brd, userStories, testCases, testData, bpmn, databaseSchema, copilotPrompt.
- **Project Management (Multi-Tenancy)**: Many-to-many user-project relationships via `user_projects` junction table. Users can belong to multiple projects. Admins see all projects; non-admin users see only their assigned projects via `/api/user-projects` endpoint. Frontend uses `useProject()` context hook for project-scoped data access. The `useAuth` hook provides both `projectId` (legacy single) and `projectIds` (array) fields.

## External Dependencies

### AI Services
- **PWC GenAI**: Primary AI provider for all text generation tasks.
  - Available models: `vertex_ai.gemini-2.5-flash-image`, `vertex_ai.gemini-2.5-pro`, `azure.gpt-5.2`, `vertex_ai.anthropic.claude-sonnet-4-6`, `azure.grok-4-fast-reasoning`
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

## Recent Changes

### True SSE Streaming for BRD Generation (Feb 2026)
- `pwc_llm.py`: Added `call_pwc_genai_stream()` async generator that yields text chunks as they arrive from PwC GenAI API (sets `stream: True` in request body, parses SSE `data:` lines with delta content). Includes fallback for non-streaming API responses.
- `generators.py`: Added `generate_brd_streaming()` async generator that yields `{"type": "chunk", "text": ...}` for each text delta and `{"type": "done", "brd": ...}` with parsed BRD at the end.
- `ai_service.py`: Added `_task_streamer()` and `generate_brd_streaming()` wrapper methods.
- `/api/brd/generate` endpoint: Refactored to use `generate_brd_streaming()` — each text chunk is sent as a separate SSE `data:` event in real-time, final parsed BRD sent as `brd` field on completion.
- `BRDPage.tsx`: Frontend SSE reader updated with proper line buffering and incremental text accumulation. Shows raw streaming text in real-time during generation, switches to structured BRD view on completion.

### Generation History Page (Feb 2026)
- Added `/generation-history` route and page that lists all generated artifacts grouped by feature request
- Backend endpoint: `GET /api/generation-history?project_id=xxx` aggregates feature_requests → BRDs → user stories/test cases/test data
- Sidebar nav entry under "History" section, accessible to all authenticated users (no feature key restriction)
- Expandable card UI: click feature request to expand and see BRDs, then click BRD to see nested user stories, test cases, and test data

### RAGAS Evaluation Framework (Feb 2026)
- **Database**: `rag_evaluations` PostgreSQL table tracking evaluation status, 5 metric scores (faithfulness, answer_relevancy, context_relevancy, context_precision, hallucination_score), overall score, chunk metadata, and detailed reasoning
- **Service**: `server_py/services/ragas_evaluation_service.py` — LLM-as-judge pattern using PWC GenAI (not the `ragas` Python library). Evaluates RAG quality of BRD generation with structured JSON scoring prompts. Includes hallucination detection that specifically identifies fabricated claims not grounded in retrieved context. Context for evaluation combines three sources: (1) MongoDB KB chunks, (2) Code Documentation from repo analysis, (3) Existing System Context (database schema, architecture, tech stack from analysis)
- **Async Trigger**: Evaluations run asynchronously via `asyncio.create_task()` after BRD generation completes (in `server_py/api/v1/requirements.py`), passing all three context sources (knowledge_sources, documentation, database_schema, analysis) to the evaluation
- **API Endpoints**: `GET /api/ragas/evaluations` (list with pagination/project filter), `GET /api/ragas/stats` (aggregate scores, quality tiers, trends), `GET /api/ragas/evaluations/{id}` (detail)
- **Admin Dashboard**: New "RAG Metrics" tab at `/admin/rag-metrics` with summary cards (overall score, faithfulness, answer relevancy, context quality), score bar visualizations, quality distribution tiers, and expandable evaluation detail table with per-metric reasoning
- **LLM Config**: `ragas_evaluation` task entry in `server_py/llm_config.yml`

### Prompt Management Migration to PostgreSQL (Feb 2026)
- **Database**: `prompts` PostgreSQL table with columns: id, prompt_key, category, content, description, prompt_type, is_active, version, created_at, updated_at. Unique constraint on (prompt_key, category, version) for versioning support.
- **Seeder**: `server_py/services/prompt_seeder.py` reads all 8 YAML files from `server_py/prompts/` and inserts into the `prompts` table at startup (idempotent — skips existing prompts). Called from `app.py` startup event after `init_postgres_database()`.
- **PromptLoader**: Updated `server_py/prompts/__init__.py` to query PostgreSQL first (active prompt, latest version), with YAML file fallback. In-memory cache with 300s TTL. `invalidate_cache()` method for clearing after updates.
- **API Endpoints**: `GET /api/prompts` (list with category/search/active filters, pagination), `GET /api/prompts/{id}` (detail with version history), `PUT /api/prompts/{id}` (admin-only, creates new version on content change), `GET /api/prompts-categories` (category summary with counts)
- **Admin UI**: New "Prompts" tab in Admin page (`client/src/components/admin/PromptManagementTab.tsx`). Category sidebar filter, search, expandable prompt cards showing content with copy/edit actions. Edit dialog creates new versions (old version deactivated).
- **Versioning**: Content updates create a new version (version + 1), deactivating the previous. PromptLoader always retrieves the latest active version. Version history viewable per prompt.