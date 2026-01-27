# DocuGen AI

## Overview

DocuGen AI is an AI-powered documentation and business requirements document (BRD) generator. The application analyzes GitHub repositories and automatically generates comprehensive technical documentation, BRDs, test cases, and test data using OpenAI's language models.

The workflow guides users through a multi-step process:
1. **Analyze Repository** - Connect and analyze a GitHub repository
2. **Documentation** - View AI-generated technical documentation
3. **Requirements** - Input feature requirements via text, file upload, or voice
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
- **Runtime**: Node.js with Express.js
- **Language**: TypeScript with ES modules
- **API Design**: RESTful JSON APIs under `/api/*` routes
- **AI Integration**: OpenAI API via Replit AI Integrations (custom base URL)
- **File Handling**: Multer for multipart form data (audio/file uploads)

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
- Repository analysis via GitHub API + OpenAI
- BRD generation with streaming responses
- Test case and test data generation
- Audio transcription for voice input (Whisper API)
- Image generation capabilities (gpt-image-1)

### Replit Integrations
The project includes pre-built integrations in `server/replit_integrations/` and `client/replit_integrations/`:
- **Audio**: Voice recording, playback, and speech-to-text
- **Chat**: Conversation storage and streaming responses
- **Image**: Image generation endpoints
- **Batch**: Rate-limited batch processing utilities

## External Dependencies

### AI Services
- **OpenAI API**: Primary AI provider accessed through Replit AI Integrations
  - Environment: `AI_INTEGRATIONS_OPENAI_API_KEY`, `AI_INTEGRATIONS_OPENAI_BASE_URL`
  - Models used: GPT for text, Whisper for audio transcription, gpt-image-1 for images

### Database
- **PostgreSQL**: Primary database (Drizzle ORM)
  - Environment: `DATABASE_URL`
  - Session store: connect-pg-simple for Express sessions

### External APIs
- **GitHub API**: Repository analysis (public endpoints, no auth required for public repos)
  - Fetches repository metadata, file trees, and file contents

### Key NPM Packages
- **Frontend**: React, TanStack Query, Radix UI, Tailwind CSS, Wouter, date-fns
- **Backend**: Express, Drizzle ORM, OpenAI SDK, Multer, Zod
- **Build**: Vite, esbuild, TypeScript

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
- `POST /api/jira/sync-subtask` - Create a single story as a JIRA subtask

### JIRA Integration Features
- **Smart Story Detection**: Before generating user stories, the app fetches existing JIRA stories and uses AI semantic search to find related ones
- **Subtask Creation**: Users can choose to create new user stories as subtasks of existing JIRA stories
- **Parent Context**: When creating subtasks, the parent story's content is used as context for more relevant generation
- **Edit Before Sync**: All user stories are editable (title, description, acceptance criteria, etc.) before syncing to JIRA

## Development Guidelines

### Running the Application
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