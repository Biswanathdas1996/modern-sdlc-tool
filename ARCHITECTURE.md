# Defuse 2.O — System Architecture

## Mermaid Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend (React + TypeScript)"
        UI[React UI<br/>shadcn/ui + Tailwind]
        TQ[TanStack Query<br/>State Management]
        WR[Wouter Router]
        SSE_Client[SSE Client<br/>Real-time Streaming]
    end

    subgraph "API Layer (FastAPI)"
        API[FastAPI Routes<br/>/api/v1/*]
        Auth[Session Auth<br/>Cookie-based]
        Guard[NeMo Guardrails<br/>Input Screening]
    end

    subgraph "Service Layer"
        AIS[AIService<br/>Orchestrator]
        GEN[Generators<br/>Prompt Assembly]
        GH[GitHub Fetcher<br/>Repo Analysis]
        KBS[Knowledge Base Service<br/>RAG Pipeline]
        SRS[Session Restore<br/>Context Recovery]
    end

    subgraph "AI Gateway (pwc_llm.py)"
        direction TB
        MTD[Model Type Detector<br/>text / multimodal / embedding / audio]
        RB[Request Builder<br/>Dynamic per model type]
        CONT[Auto-Continuation<br/>Long response handling]
        LF[Langfuse Tracing<br/>Observability]
        
        MTD --> RB
        RB --> CONT
        CONT --> LF
    end

    subgraph "LLM Config (llm_config.yml)"
        CFG[26 Task-specific Entries<br/>Model + Temp + MaxTokens per task]
    end

    subgraph "Specialized AI Agents"
        direction TB
        
        subgraph "JIRA Agent"
            JA[Orchestrator<br/>LangChain AgentExecutor]
            JT[13 Tools<br/>create/update/search/link]
            JDP[Direct Processor<br/>Fallback routing]
            JCV[Conversation Context<br/>Multi-turn memory]
        end

        subgraph "Unit Test Agent"
            UTA[Orchestrator<br/>Threaded pipeline]
            UTT[10 Tools<br/>analyze/discover/generate/fix/run]
            UTH[4 Helpers<br/>deps/mocking/npm/paths]
            UTU[3 Utils<br/>errors/imports/patterns]
        end

        subgraph "Security Agent (Shannon)"
            SA[Orchestrator<br/>Multi-phase assessment]
            SAT[9 Tools<br/>recon/crawl/inject/CVE/analyze]
        end

        subgraph "Code Gen Agent"
            CGA[Orchestrator<br/>Plan → Implement → Push]
            CGT[GitHub Integration<br/>Clone/Analyze/Push]
        end

        subgraph "Web Test Agent"
            WTA[Orchestrator<br/>Scrape → Analyze → Report]
            WTT[Playwright + httpx<br/>SPA-aware scraping]
        end
    end

    subgraph "Data Layer"
        PG[(PostgreSQL<br/>All domain entities<br/>JSONB columns)]
        MDB[(MongoDB Atlas<br/>Per-project KB collections<br/>Vector search)]
        EMBED[fastembed<br/>BAAI/bge-small-en-v1.5<br/>384-dim local embeddings]
    end

    subgraph "External Services"
        PWC[PwC GenAI API<br/>Multi-model gateway]
        GHAPI[GitHub API<br/>Repo metadata + files]
        JIRA_API[JIRA Cloud API<br/>Issues + Search]
        CONF[Confluence API<br/>Publishing]
    end

    UI --> TQ --> API
    SSE_Client -.->|streaming| API
    API --> Auth
    API --> AIS
    AIS --> GEN
    AIS --> GH
    AIS --> SRS
    GEN --> KBS
    KBS --> MDB
    KBS --> EMBED
    
    API --> JA
    API --> UTA
    API --> SA
    API --> CGA
    API --> WTA

    AIS --> Guard
    Guard --> MTD
    CFG -.->|task_name lookup| MTD
    LF --> PWC

    GH --> GHAPI
    JA --> JIRA_API
    JA --> CONF

    SRS --> PG
    AIS --> PG

    JA --> JT
    JA --> JDP
    JA --> JCV
    UTA --> UTT
    UTA --> UTH
    SA --> SAT
    CGA --> CGT --> GHAPI
    WTA --> WTT
```

## Detailed Agent Workflow Diagrams

### BRD Generation Pipeline (SSE Streaming)

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant SessionRestore
    participant KnowledgeBase
    participant AIService
    participant PWC_LLM
    participant PostgreSQL
    participant MongoDB

    User->>Frontend: Submit feature request
    Frontend->>API: POST /api/brd/generate (SSE)
    API->>SessionRestore: Restore feature_request, analysis, docs, db_schema
    SessionRestore->>PostgreSQL: Fetch stored contexts
    PostgreSQL-->>SessionRestore: Return contexts
    
    API->>KnowledgeBase: search_knowledge_base(project_id, query)
    KnowledgeBase->>MongoDB: Vector similarity search (cosine)
    MongoDB-->>KnowledgeBase: Top chunks above threshold
    
    Note over API: Assemble multi-source context:<br/>1. Feature Request<br/>2. Repo Analysis<br/>3. Technical Docs<br/>4. DB Schema<br/>5. Knowledge Base chunks
    
    API->>AIService: generate_brd(all_context)
    AIService->>PWC_LLM: call_pwc_genai_async(prompt, task="brd_generation")
    
    Note over PWC_LLM: Model: gemini-2.5-pro<br/>Auto-continuation if truncated
    
    loop SSE Streaming
        PWC_LLM-->>API: Response chunks
        API-->>Frontend: SSE event: chunk
        Frontend-->>User: Real-time rendering
    end
    
    API->>PostgreSQL: Store BRD with created_by
    API-->>Frontend: SSE event: done
```

### Unit Test Agent Pipeline

```mermaid
sequenceDiagram
    participant User
    participant API
    participant Agent
    participant GitHub
    participant LLM
    participant NPM

    User->>API: POST /unit-test-agent/chat
    API->>Agent: Start generation task (threaded)
    Agent->>GitHub: Clone repository
    
    Agent->>LLM: analyze_repo (detect language, framework)
    LLM-->>Agent: {language: "javascript", framework: "react", test_framework: "jest"}
    
    Agent->>Agent: discover_existing_tests
    Agent->>LLM: analyze_test_patterns (learn project style)
    Agent->>Agent: collect_source_files
    Agent->>LLM: coverage_mapper (identify gaps)
    
    Agent->>NPM: npm install (if needed)
    NPM-->>Agent: Dependencies ready
    
    loop For each uncovered source file
        Agent->>LLM: generate_tests_for_file (with style guide + deps context)
        LLM-->>Agent: Test code
        Agent->>Agent: write_test_file
        Agent->>NPM: run_test_file
        
        alt Tests pass
            Agent->>Agent: Mark as validated ✅
        else Tests fail
            loop Up to 3 fix attempts
                Agent->>LLM: fix_tests (with error output)
                LLM-->>Agent: Fixed test code
                Agent->>NPM: run_test_file
            end
        end
    end
    
    Agent->>Agent: Generate coverage report
    Agent-->>API: Complete with results
    
    loop Polling
        User->>API: GET /unit-test-agent/task/{id}
        API-->>User: Status + thinking steps
    end
```

### JIRA Agent (Multi-turn Conversational)

```mermaid
sequenceDiagram
    participant User
    participant API
    participant IntentAnalyzer
    participant Agent
    participant DirectProcessor
    participant JIRATools
    participant JIRA_API

    User->>API: POST /jira/chat "Create a login story"
    API->>IntentAnalyzer: Classify intent
    IntentAnalyzer->>IntentAnalyzer: LLM intent extraction (Gemini Flash)
    IntentAnalyzer-->>API: {action: "create", type: "story"}
    
    alt LangChain Agent available
        API->>Agent: AgentExecutor.run()
        Agent->>JIRATools: select_tool(intent)
        JIRATools->>JIRA_API: Create issue
    else Fallback to Direct Processing
        API->>DirectProcessor: direct_process(prompt, intent)
        DirectProcessor->>DirectProcessor: Route by action type
        DirectProcessor->>JIRATools: Execute operation
        JIRATools->>JIRA_API: REST API call
    end
    
    JIRA_API-->>JIRATools: Issue created
    JIRATools-->>API: Formatted response
    API-->>User: "Created KAN-23: Login Story"
```

### Security Agent (Shannon) — Multi-Phase Assessment

```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant Tools
    participant LLM
    participant Target

    User->>Agent: "Assess https://example.com"
    
    Note over Agent: Phase 1: Reconnaissance
    Agent->>Tools: gather_web_context(url)
    Tools->>Target: HTTP headers, tech detection
    Target-->>Tools: Server info, frameworks
    
    Note over Agent: Phase 2: Crawling
    Agent->>Tools: crawl_site(url)
    Tools->>Target: Spider pages, forms, links
    Target-->>Tools: Site map + form inventory
    
    Note over Agent: Phase 3: Directory Enumeration
    Agent->>Tools: enumerate_directories(url)
    Tools->>Target: Common path brute-force
    Target-->>Tools: Exposed paths
    
    Note over Agent: Phase 4: Injection Testing
    Agent->>Tools: test_form_injections(forms)
    Tools->>Target: XSS, SQLi payloads
    Target-->>Tools: Vulnerability findings
    
    Note over Agent: Phase 5: Method Testing
    Agent->>Tools: test_http_methods(url)
    Tools->>Target: OPTIONS, PUT, DELETE
    Target-->>Tools: Allowed methods
    
    Note over Agent: Phase 6: CVE Lookup
    Agent->>Tools: lookup_cves(tech_stack)
    Tools-->>Agent: Known vulnerabilities
    
    Note over Agent: Phase 7: AI Analysis
    Agent->>LLM: Synthesize all findings
    LLM-->>Agent: Security report + risk scores
    
    Agent-->>User: Full assessment report
```

---

## What Makes Defuse 2.O Powerful — Key Differentiators

### 1. Multi-Source Context Assembly (No One Else Does This)
Most AI doc generators just take a prompt and generate. Defuse assembles **5 independent context sources** before every BRD generation:
- **GitHub repo analysis** (architecture, tech stack, features)
- **Generated technical documentation** 
- **External database schema** (live PostgreSQL introspection)
- **Knowledge base documents** (RAG with vector search)
- **Feature request details** (user input)

This means the AI has deep, project-specific understanding — not generic output.

### 2. Per-Project Knowledge Base with Vector Search (RAG)
- Each project gets its **own MongoDB collections** (`knowledge_chunks_{project_id}`, `knowledge_documents_{project_id}`)
- Documents are chunked with **section-aware splitting** (breaks at headings, paragraphs, sentences — not arbitrary character cuts)
- **384-dim local embeddings** via fastembed (BAAI/bge-small-en-v1.5) — no external embedding API needed
- **Cosine similarity search with threshold filtering** — only includes genuinely relevant chunks, never dilutes with weak matches
- **Re-ingestion API** to update embeddings when chunking strategy improves

### 3. Self-Healing Unit Test Generation
The unit test agent doesn't just generate tests — it **validates and fixes them**:
1. Generates tests per file (not one giant batch)
2. Actually **runs each test** against the real project
3. If tests fail, feeds errors back to the LLM for **auto-fix** (up to 3 attempts)
4. Extracts only passing tests if fixes fail
5. Only delivers **100% passing** test suites

No other tool does this — most just generate and hope.

### 4. Dynamic Multi-Model LLM Routing
- **26 task-specific entries** in `llm_config.yml` — each task gets the optimal model
- `pwc_llm.py` **auto-detects model type** (text/multimodal/embedding/audio) and adjusts request format
- Anthropic models automatically get `top_p` stripped (avoids API errors)
- **Auto-continuation** for long responses — if the model hits token limit, it automatically continues
- **Langfuse tracing** on every call for full observability

### 5. NeMo Guardrails on Every LLM Call
Every prompt passes through **NeMo Guardrails** before reaching the LLM:
- Keyword blocklist scanning
- Prompt injection detection
- Only scans the **current user input** (not conversation history) to avoid false positives
- Graceful degradation — if guardrails fail to initialize, calls proceed with a warning

### 6. Agentic Architecture with Fallbacks
- **JIRA Agent**: LangChain AgentExecutor with 13 tools + fallback to direct processing if agent fails
- **Security Agent**: 7-phase assessment pipeline (recon → crawl → enumerate → inject → methods → CVEs → AI analysis)
- **Code Gen Agent**: Plan → implement → push to GitHub — full autonomous cycle
- **Web Test Agent**: Playwright for SPAs, httpx fallback for simpler sites

### 7. User-Level Data Isolation
- `created_by` field on feature requests and BRDs
- Each user sees only their own work within a project
- Legacy records (NULL `created_by`) remain visible via fallback — no data loss during migration

### 8. SSE Streaming for BRD Generation
BRDs stream in real-time via Server-Sent Events — users see content appearing live instead of waiting for the full document. This is combined with the multi-source context assembly for a unique "deep + fast" experience.

### 9. Modular Agent Architecture (80+ Python files)
Each agent follows the same pattern:
```
agent/
├── agent.py          # Slim orchestrator
├── tools/            # Capability modules (one function per tool)
├── helpers/          # Domain-specific helpers
└── utils/            # Pure utilities
```
One-way dependency: `tools → helpers/utils` only. No circular imports.

### 10. Full SDLC Coverage in One Platform
```
Repo Analysis → Documentation → Feature Requests → BRDs → User Stories → 
Test Cases → Test Data → Unit Tests → Code Generation → JIRA Sync → 
Confluence Publishing → Security Assessment → Web Testing
```
No other single tool covers this entire pipeline with AI at every step.

---

## Summary: The Defuse 2.O Difference

| What Others Do | What Defuse 2.O Does |
|---|---|
| Single LLM model for everything | 5 models optimally assigned to 26 tasks |
| Generic prompts | 5-source context assembly per generation |
| Generate tests and hope | Generate → Run → Fix → Validate (self-healing) |
| One global knowledge base | Per-project isolated KB with vector search |
| Single-user design | User-level isolation with `created_by` tracking |
| Wait for full response | SSE streaming with live rendering |
| Basic input validation | NeMo Guardrails on every LLM call |
| Agent or nothing | Agent + direct processing fallback |
| Manual JIRA updates | Conversational AI agent with 13 tools |
| Separate security tools | 7-phase automated pentesting pipeline |
