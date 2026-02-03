# DocuGen AI

## Overview

DocuGen AI is an AI-powered documentation and business requirements document (BRD) generator. The application analyzes GitHub repositories and automatically generates comprehensive technical documentation, BRDs, test cases, and test data using PWC GenAI (Gemini 2.0 Flash model).

The workflow guides users through a multi-step process:
1. **Analyze Repository** - Connect and analyze a GitHub repository
2. **Documentation** - View AI-generated technical documentation
3. **Requirements** - Input feature requirements via text or file upload (voice input disabled)
4. **BRD Generation** - Generate business requirements documents
5. **Test Cases** - Generate test cases from BRDs
6. **Test Data** - Generate test data for test cases

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: React 18 with TypeScript
- **Routing**: Wouter (lightweight React router)
- **State Management**: TanStack Query (React Query) for server state
- **UI Components**: shadcn/ui component library built on Radix UI primitives
- **Styling**: Tailwind CSS with CSS variables for theming (light/dark mode support)
- **Build Tool**: Vite with custom plugins for Replit integration

### Backend Architecture
**Python/FastAPI Backend (Primary - Converted from Node.js)**
- **Runtime**: Python 3.11 with FastAPI
- **Language**: Python with async/await support
- **API Design**: RESTful JSON APIs under `/api/*` routes (same endpoints as Node.js version)
- **AI Integration**: PWC GenAI (Gemini 2.0 Flash) via httpx async client
- **File Handling**: python-multipart for file uploads, PyPDF2 and python-docx for parsing
- **SSE Streaming**: sse-starlette for BRD generation streaming
- **Database**: psycopg2 for PostgreSQL schema introspection
- **MongoDB**: pymongo for knowledge base operations
- **Location**: `server_py/` directory

**Legacy Node.js Backend (Original)**
- **Runtime**: Node.js with Express.js
- **Language**: TypeScript with ES modules
- **Location**: `server/` directory

### Data Storage
- **ORM**: Drizzle ORM with PostgreSQL dialect
- **Schema Location**: `shared/schema.ts` contains Zod schemas for validation
- **Database Models**: Projects, RepoAnalysis, Documentation, FeatureRequests, BRDs, TestCases, TestData
- **Storage Pattern**: In-memory storage implementation (`server/storage.ts`) with interface for database migration

### Key Design Patterns
- **Shared Types**: Schema definitions in `shared/` directory are used by both client and server
- **Path Aliases**: `@/` for client source, `@shared/` for shared code
- **Component Architecture**: Reusable UI components in `components/ui/`, custom components in `components/`
- **Page-based Routing**: Each workflow step has a dedicated page component

### AI Features
- Repository analysis via GitHub API + PWC GenAI
- BRD generation (non-streaming due to PWC GenAI limitation)
- Test case and test data generation
- User story and Copilot prompt generation
- BPMN business flow diagram generation

### Disabled Features (PWC GenAI Only Supports Text)
The following features are disabled because PWC GenAI only supports text generation:
- **Audio**: Voice input/transcription (Whisper API not available)
- **Image**: Image generation (gpt-image-1 not available)
- **Embeddings**: Vector search (using text-based search fallback for Knowledge Base)

## External Dependencies

### AI Services
- **PWC GenAI**: Primary AI provider for all text generation
  - Environment: `PWC_GENAI_ENDPOINT_URL`, `PWC_GENAI_API_KEY`, `PWC_GENAI_BEARER_TOKEN`
  - Model: vertex_ai.gemini-2.0-flash (text generation only)

### Database
- **PostgreSQL**: Primary database (Drizzle ORM)
  - Environment: `DATABASE_URL`
  - Session store: connect-pg-simple for Express sessions

### External APIs
- **GitHub API**: Repository analysis (public endpoints, no auth required for public repos)
  - Fetches repository metadata, file trees, and file contents

### Key NPM Packages
- **Frontend**: React, TanStack Query, Radix UI, Tailwind CSS, Wouter, date-fns
- **Build**: Vite, esbuild, TypeScript

### Python Packages (Backend)
- **Web Framework**: FastAPI, uvicorn, starlette
- **HTTP Client**: httpx (async)
- **Validation**: pydantic
- **File Parsing**: PyPDF2, python-docx
- **SSE**: sse-starlette
- **Database**: psycopg2-binary, pymongo
- **Utilities**: python-dotenv, aiofiles, python-multipart

## Recent Changes (January 2026)

### Design System
- Configured GitHub-inspired color palette (Primary: #0366D6, Success: #28A745)
- Added JetBrains Mono for code blocks and monospace text
- Implemented dark/light mode support with smooth transitions
- Created custom prose styling for documentation rendering

### Frontend Components Built
- `AppSidebar` - Multi-step workflow navigation with progress indicators
- `WorkflowHeader` - Step progress visualization
- `CodeBlock` - Syntax-highlighted code with copy functionality
- `DocumentPreview` - Rich document rendering with export
- `LoadingSpinner/LoadingOverlay` - AI processing feedback
- `EmptyState` - Helpful empty state messages
- `ThemeProvider/ThemeToggle` - Dark mode support
- `MermaidDiagram` - Renders Mermaid.js flowcharts for BPMN diagrams (strict security mode)

### Pages Implemented
- `AnalyzePage` - Repository URL input and project listing
- `DocumentationPage` - Generated docs with table of contents
- `RequirementsPage` - Text/file/audio input with tabs
- `BRDPage` - Business requirements with streaming generation
- `TestCasesPage` - Test case viewing with filters
- `TestDataPage` - Test data with JSON/table views

### Backend APIs
- `POST /api/projects/analyze` - Analyze GitHub repository
- `GET /api/projects` - List all projects
- `POST /api/requirements` - Submit feature requirements (supports file/audio)
- `POST /api/brd/generate` - Generate BRD with SSE streaming
- `POST /api/user-stories/generate` - Generate user stories (supports parentJiraKey for subtasks)
- `PATCH /api/user-stories/:id` - Update a user story
- `POST /api/test-cases/generate` - Generate test cases
- `POST /api/test-data/generate` - Generate test data
- `POST /api/jira/sync` - Sync user stories to JIRA (creates stories or subtasks)
- `GET /api/jira/stories` - Fetch existing stories from JIRA board
- `POST /api/jira/find-related` - Semantic search for related JIRA stories
- `GET /api/bpmn/current` - Get BPMN user journey diagrams for current documentation
- `POST /api/jira/sync-subtask` - Create a single story as a JIRA subtask
- `POST /api/database-schema/connect` - Connect to external PostgreSQL and fetch schema
- `GET /api/database-schema/current` - Get current database schema for project
- `DELETE /api/database-schema/current` - Remove database schema from project
- `POST /api/confluence/publish` - Publish BRD to Confluence page

### External Database Schema Integration
- **Connect to External PostgreSQL**: Users can paste a PostgreSQL connection string to fetch table schema
- **Schema Storage**: Tables, columns, data types, primary keys, foreign keys, and row counts are stored
- **Password Masking**: Connection strings are masked before storage for security
- **AI Context Integration**: Database schema is included in AI prompts for BRD, User Stories, and Copilot Prompts
- **Visual Display**: Schema is displayed in collapsible table view on Documentation page

### Request Type Tabs
- **New Feature Tab**: Creates JIRA Stories for new functionality requests
- **Bug Report Tab**: Creates JIRA Bugs with reproduction-focused tips and placeholders
- **Change Request Tab**: Creates JIRA Tasks for modifications to existing functionality
- **Context-Specific UI**: Each tab has tailored placeholders, tips, and JIRA issue type badges

### JIRA Integration Features
- **Smart Story Detection**: Before generating user stories, the app fetches existing JIRA stories and uses AI semantic search to find related ones
- **Subtask Creation**: Users can choose to create new user stories as subtasks of existing JIRA stories
- **Parent Context**: When creating subtasks, the parent story's content is used as context for more relevant generation
- **Edit Before Sync**: All user stories are editable (title, description, acceptance criteria, etc.) before syncing to JIRA
- **Dynamic Issue Types**: Creates Story/Bug/Task based on request type from Requirements page

### Confluence Integration
- **Publish to Confluence**: Button on BRD page to publish generated BRDs to Confluence
- **Same Credentials**: Uses JIRA_EMAIL and JIRA_API_TOKEN (same Atlassian account)
- **ADF Format**: Converts BRD content to Atlassian Document Format for proper rendering
- **Full Content Export**: Includes overview, objectives, scope, requirements, risks, and metadata
- **Environment Variables**: CONFLUENCE_SPACE_KEY for target space (defaults to personal space)

### BPMN Business Flow Diagram
- **Automatic Generation**: After documentation is generated, a comprehensive BPMN diagram is automatically created
- **Mermaid.js Rendering**: Flowchart is rendered using Mermaid.js with strict security mode
- **Complete Business Flow**: Single diagram shows the entire end-to-end business process with all workflow stages
- **Visual Documentation**: Diagram appears in the "Business Flow" section of the Documentation page

### Knowledge Base (RAG System)
- **MongoDB Atlas Integration**: Uses MongoDB Atlas with vector search for semantic document retrieval
- **Document Upload**: Drag-and-drop support for TXT, MD, JSON, CSV files in Knowledge Base page
- **Text Chunking**: Documents split into 1000-character chunks with 200-character overlap for optimal retrieval
- **Vector Embeddings**: Uses OpenAI text-embedding-3-small model (1536 dimensions) for semantic search
- **Automatic RAG Integration**: Knowledge base is automatically searched during BRD and user story generation
- **Fallback Search**: If vector search fails, falls back to text-based search for reliability
- **Status Tracking**: Documents show processing/ready/error status with chunk counts

### Knowledge Base APIs
- `POST /api/knowledge-base/upload` - Upload document with automatic chunking and embedding
- `GET /api/knowledge-base` - List all uploaded documents
- `GET /api/knowledge-base/stats` - Get document and chunk counts
- `DELETE /api/knowledge-base/:id` - Remove document from knowledge base
- `POST /api/knowledge-base/search` - Semantic search across knowledge base

## Development Guidelines

### Running the Application

**Python Backend (Recommended)**
```bash
./run-python-backend.sh
```
This starts the Python FastAPI backend on port 5000 with Vite dev server on port 5173 for hot-reload.

Alternatively, run components separately:
```bash
# Terminal 1: Start Vite dev server
npx vite --port 5173

# Terminal 2: Start Python backend
cd server_py && python main.py
```

**Legacy Node.js Backend**
```bash
npm run dev
```
This starts the Express backend and Vite frontend on port 5000.

### Adding New Pages
1. Create component in `client/src/pages/`
2. Add route in `client/src/App.tsx`
3. Update sidebar in `client/src/components/AppSidebar.tsx`

### Styling Guidelines
- Use semantic color variables (--primary, --success, etc.)
- Follow design system in `client/src/index.css`
- Use `prose-docs` class for markdown-like content
- Use `hover-elevate` for interactive hover states