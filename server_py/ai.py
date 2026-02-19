import os
import re
import json
import httpx
from typing import Optional, Dict, Any, List, Callable

GENAI_ENDPOINT = os.environ.get("PWC_GENAI_ENDPOINT_URL", "")
API_KEY = os.environ.get("PWC_GENAI_API_KEY", "")
BEARER_TOKEN = os.environ.get("PWC_GENAI_BEARER_TOKEN", "")


async def call_pwc_genai(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
    if not API_KEY or not BEARER_TOKEN or not GENAI_ENDPOINT:
        raise ValueError(
            "PwC GenAI credentials not configured. Please provide PWC_GENAI_API_KEY, "
            "PWC_GENAI_BEARER_TOKEN, and PWC_GENAI_ENDPOINT_URL."
        )

    request_body = {
        "model": "vertex_ai.gemini-2.0-flash",
        "prompt": prompt,
        "temperature": temperature,
        "top_p": 1,
        "presence_penalty": 0,
        "stream": False,
        "stream_options": None,
        "seed": 25,
        "stop": None,
    }

    headers = {
        "accept": "application/json",
        "API-Key": API_KEY,
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json",
    }

    print(f"Calling PwC GenAI with prompt length: {len(prompt)}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(GENAI_ENDPOINT, json=request_body, headers=headers)

    if response.status_code != 200:
        print(f"PwC GenAI API error: {response.status_code} - {response.text}")
        raise ValueError(f"PwC GenAI API Error: {response.status_code} - {response.text}")

    result = response.json()
    print(f"PwC GenAI API response received: {list(result.keys())}")

    if "choices" in result and len(result["choices"]) > 0:
        choice = result["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"]
        if "text" in choice:
            return choice["text"]
    if "text" in result:
        return result["text"]
    if "content" in result:
        return result["content"]

    raise ValueError("Unexpected response format from PwC GenAI API")


def build_prompt(system_message: str, user_message: str) -> str:
    return f"System: {system_message}\n\nUser: {user_message}"


def _fix_invalid_escapes(text: str) -> str:
    valid_escapes = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            if next_char in valid_escapes:
                result.append(text[i])
                result.append(next_char)
                i += 2
            else:
                result.append('\\\\')
                result.append(next_char)
                i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _fix_truncated_json(text: str) -> str:
    text = text.rstrip()
    if text.endswith(","):
        text = text[:-1]
    
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
    
    if in_string:
        text += '"'

    text = text.rstrip().rstrip(",")
    
    for _ in range(open_braces):
        text += "}"
    for _ in range(open_brackets):
        text += "]"
    
    return text


def _sanitize_json_string_values(text: str) -> str:
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '\\' and in_string and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
                result.append(ch)
                result.append(next_ch)
                i += 2
                continue
            else:
                result.append('\\\\')
                i += 1
                continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                if i + 1 < len(text) and text[i + 1] not in (',', '}', ']', ':', '\n', '\r', ' ', '\t'):
                    result.append('\\"')
                else:
                    in_string = False
                    result.append(ch)
            i += 1
            continue
        if in_string and ch in ('\n', '\r', '\t'):
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            i += 1
            continue
        result.append(ch)
        i += 1
    return ''.join(result)


def parse_json_response(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    stripped = cleaned.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as first_error:
        print("First JSON parse failed, attempting escape fix...")
        
        try:
            fixed = _fix_invalid_escapes(stripped)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        
        print("Attempting sanitize fix...")
        try:
            sanitized = _sanitize_json_string_values(stripped)
            return json.loads(sanitized)
        except json.JSONDecodeError:
            pass
        
        print("Attempting truncated JSON fix...")
        try:
            truncated_fix = _fix_truncated_json(stripped)
            return json.loads(truncated_fix)
        except json.JSONDecodeError:
            pass
        try:
            truncated_fix = _fix_truncated_json(_sanitize_json_string_values(stripped))
            return json.loads(truncated_fix)
        except json.JSONDecodeError:
            pass
        
        print("Attempting regex extraction...")
        
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            candidate = array_match.group(0)
            for attempt_fn in [
                lambda t: t,
                _fix_invalid_escapes,
                _sanitize_json_string_values,
                lambda t: _fix_truncated_json(_sanitize_json_string_values(t)),
            ]:
                try:
                    return json.loads(attempt_fn(candidate))
                except:
                    pass

        object_match = re.search(r'\{[\s\S]*\}', text)
        if object_match:
            candidate = object_match.group(0)
            for attempt_fn in [
                lambda t: t,
                _fix_invalid_escapes,
                _sanitize_json_string_values,
                lambda t: _fix_truncated_json(_sanitize_json_string_values(t)),
            ]:
                try:
                    return json.loads(attempt_fn(candidate))
                except:
                    pass
        
        raise ValueError(f"Failed to parse JSON from response. Original error: {first_error}. Response preview: {text[:200]}...")


def get_github_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "DocuGen-AI",
    }
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch_repo_contents(repo_url: str) -> str:
    import base64
    
    match = re.match(r"github\.com/([^/]+)/([^/]+)", repo_url.replace("https://", ""))
    if not match:
        raise ValueError("Invalid GitHub URL")

    owner = match.group(1)
    repo = match.group(2).replace(".git", "")
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=60.0) as client:
        repo_response = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        if repo_response.status_code != 200:
            raise ValueError(f"Failed to fetch repository: {repo_response.status_code}")
        repo_data = repo_response.json()

        default_branch = repo_data.get("default_branch", "main")

        tree_response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
            headers=headers
        )
        tree_data = {"tree": []}
        if tree_response.status_code == 200:
            tree_data = tree_response.json()

    code_extensions = [
        '.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.go', '.rs', '.rb', '.php',
        '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
        '.json', '.yaml', '.yml', '.toml', '.xml', '.md', '.txt',
        '.sql', '.graphql', '.prisma', '.env.example', '.gitignore',
        '.sh', '.bash', '.zsh', '.dockerfile', '.config.js', '.config.ts'
    ]

    def is_code_file(path: str) -> bool:
        path_lower = path.lower()
        if any(x in path_lower for x in ['node_modules/', '/dist/', '/build/', '/.git/', '/coverage/', '/.next/']):
            return False
        return any(path_lower.endswith(ext) for ext in code_extensions) or \
               '.' not in path.split('/')[-1] or \
               path_lower.endswith('dockerfile') or path_lower.endswith('makefile')

    all_files = [
        {"path": f["path"], "size": f.get("size", 0)}
        for f in tree_data.get("tree", [])
        if f.get("type") == "blob" and is_code_file(f["path"])
    ]

    def priority_order(path: str) -> int:
        lower = path.lower()
        if lower == 'readme.md': return 0
        if lower == 'package.json': return 1
        if any(x in lower for x in ['index.', 'main.', 'app.']): return 2
        if lower.startswith('src/'): return 3
        if '/components/' in lower: return 4
        if '/pages/' in lower: return 5
        if any(x in lower for x in ['/api/', '/routes/']): return 6
        if any(x in lower for x in ['/services/', '/hooks/']): return 7
        if any(x in lower for x in ['/utils/', '/lib/']): return 8
        if 'config' in lower: return 9
        return 10

    all_files.sort(key=lambda f: priority_order(f["path"]))

    files_to_fetch = all_files[:50]
    file_contents = []
    total_chars = 0
    max_total_chars = 100000

    async def fetch_file(file_path: str) -> Optional[Dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    if "content" in data:
                        decoded = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
                        return {"path": file_path, "content": decoded}
        except Exception as e:
            print(f"Error fetching {file_path}: {e}")
        return None

    for i in range(0, len(files_to_fetch), 10):
        if total_chars >= max_total_chars:
            break
        batch = files_to_fetch[i:i+10]
        import asyncio
        results = await asyncio.gather(*[fetch_file(f["path"]) for f in batch])
        
        for result in results:
            if result and total_chars < max_total_chars:
                max_file_chars = 4000
                content = result["content"]
                if len(content) > max_file_chars:
                    content = content[:max_file_chars] + "\n... [truncated - file continues]"
                file_contents.append(f"\n=== FILE: {result['path']} ===\n{content}")
                total_chars += len(content)

    dir_structure = {}
    for f in all_files:
        parts = f["path"].split("/")
        dir_name = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
        if dir_name not in dir_structure:
            dir_structure[dir_name] = []
        dir_structure[dir_name].append(parts[-1])

    structure_text = "\n\n".join([
        f"{dir}/\n  " + "\n  ".join(files[:20]) + (f"\n  ... and {len(files) - 20} more files" if len(files) > 20 else "")
        for dir, files in list(dir_structure.items())[:30]
    ])

    print(f"Fetched {len(file_contents)} files, {total_chars} total characters for {owner}/{repo}")

    return f"""
=== REPOSITORY INFORMATION ===
Repository: {repo_data.get('full_name', '')}
Description: {repo_data.get('description') or 'No description provided'}
Primary Language: {repo_data.get('language') or 'Unknown'}
Stars: {repo_data.get('stargazers_count', 0)}
Forks: {repo_data.get('forks_count', 0)}
Topics: {', '.join(repo_data.get('topics', [])) or 'None'}
Default Branch: {default_branch}
License: {repo_data.get('license', {}).get('name') if repo_data.get('license') else 'Not specified'}
Total Files Analyzed: {len(file_contents)}

=== DIRECTORY STRUCTURE ===
{structure_text}

=== COMPLETE FILE CONTENTS ===
{"".join(file_contents)}
    """.strip()


async def analyze_repository(repo_url: str, project_id: str) -> Dict[str, Any]:
    repo_context = await fetch_repo_contents(repo_url)

    system_prompt = """You are a senior software architect analyzing GitHub repositories. Carefully examine ALL provided file contents, directory structure, and code to generate an ACCURATE and DETAILED analysis.

IMPORTANT INSTRUCTIONS:
1. Read EVERY file content provided - each file reveals important details
2. Extract EXACT feature names, component names, and function names from the actual code
3. Identify the REAL purpose from the code logic, not generic descriptions
4. List ACTUAL dependencies from package.json or similar config files
5. Describe the SPECIFIC architecture based on the directory structure and imports
6. Do NOT make up features that don't exist in the code
7. Do NOT use generic descriptions - be specific to THIS repository

Return your analysis as a JSON object with this exact structure:
{
  "summary": "Specific description of what this application does based on the actual code",
  "architecture": "Detailed description of the architectural patterns observed in the code structure",
  "features": [
    {
      "name": "Actual feature name from the code",
      "description": "What this feature does based on examining the code",
      "files": ["actual/file/paths.tsx", "from/the/repo.ts"]
    }
  ],
  "techStack": {
    "languages": ["languages from package.json/actual files"],
    "frameworks": ["exact framework names and versions from dependencies"],
    "databases": ["databases if referenced in code"],
    "tools": ["actual tools found in config files"]
  },
  "testingFramework": "Testing framework from devDependencies if any",
  "codePatterns": ["patterns actually observed in the code like hooks, components, services, etc"]
}"""

    user_prompt = f"Analyze this repository carefully. Read all file contents and provide an accurate analysis:\n\n{repo_context}"
    
    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_pwc_genai(prompt)
    
    analysis_data = parse_json_response(response_text)
    
    return {
        **analysis_data,
        "projectId": project_id,
    }


async def generate_documentation(analysis: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
    repo_context = ""
    try:
        repo_context = await fetch_repo_contents(project["repoUrl"])
        print(f"Documentation: Re-fetched repo contents for {project['name']}")
    except Exception as err:
        print(f"Failed to fetch repo for documentation: {err}")

    system_prompt = """You are a technical writer creating ACCURATE and DETAILED documentation for a software project. You have access to the ACTUAL SOURCE CODE files. Read them carefully and generate documentation that EXACTLY matches what the code does.

CRITICAL INSTRUCTIONS:
1. READ the actual file contents provided - they contain the real implementation
2. Extract EXACT component names, function names, and features from the code
3. Document what each file ACTUALLY does based on its code
4. Include REAL dependencies from package.json
5. Do NOT invent features that don't exist in the code
6. Do NOT use placeholder or example content - everything must come from the actual code
7. If you see a component like "CardOnboarding" in the code, document "CardOnboarding" - not a generic name

Return a JSON object with this structure:
{
  "title": "Project Name - Technical Documentation",
  "content": "Full markdown overview based on actual code",
  "sections": [
    {"title": "Overview", "content": "Description based on README and actual code purpose"},
    {"title": "Architecture", "content": "Architecture based on actual file structure and imports"},
    {"title": "Features", "content": "Features extracted from actual components and functions in the code"},
    {"title": "Components", "content": "List of actual React/UI components found in the code with their purposes"},
    {"title": "Technology Stack", "content": "Technologies from package.json dependencies"},
    {"title": "API/Services", "content": "Any API endpoints or services found in the code"},
    {"title": "Getting Started", "content": "Based on package.json scripts and README"},
    {"title": "Project Structure", "content": "Actual file structure from the repository"}
  ]
}"""

    user_prompt = f"""Generate accurate technical documentation by reading the ACTUAL SOURCE CODE below.

Project Name: {project['name']}
Repository URL: {project['repoUrl']}

=== ACTUAL SOURCE CODE FILES ===
{repo_context}

=== ANALYSIS SUMMARY (for reference) ===
- Summary: {analysis.get('summary', '')}
- Tech Stack: {json.dumps(analysis.get('techStack', {}), indent=2)}
- Features Found: {json.dumps(analysis.get('features', []), indent=2)}"""

    prompt = build_prompt(system_prompt, user_prompt)
    raw_content = await call_pwc_genai(prompt)

    try:
        doc_data = parse_json_response(raw_content)
    except Exception as parse_error:
        print(f"Failed to parse documentation JSON, attempting recovery: {parse_error}")
        doc_data = {
            "title": f"{project['name']} Documentation",
            "content": f"# {project['name']}\n\n{analysis.get('summary', 'Documentation for this repository.')}",
            "sections": []
        }

    return {
        "projectId": project["id"],
        "title": doc_data.get("title", f"{project['name']} Documentation"),
        "content": doc_data.get("content", analysis.get("summary", "")),
        "sections": doc_data.get("sections", []),
    }


async def generate_bpmn_diagram(documentation: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = """You are an expert at creating professional BPMN-style business flow diagrams using Mermaid.js flowchart syntax.

Create a SINGLE comprehensive flowchart that shows the ENTIRE business flow of the application from start to finish.

STRICT MERMAID SYNTAX RULES - FOLLOW EXACTLY:
1. Start with exactly: flowchart TD
2. Node definitions - NEVER use parentheses, quotes, or special chars in labels:
   - Start/End terminals: A([Start]) or Z([End])
   - Process boxes: B[Process Name]
   - Decision diamonds: C{Is Valid}
   - Database/Storage: D[(Database)]
3. Subgraph syntax:
   - subgraph SubgraphID[Display Name]
   - end
4. Arrow connections:
   - Simple: A --> B
   - With label: A -->|Yes| B
5. Keep labels SHORT: 2-4 words maximum, no special characters
6. Use simple alphanumeric IDs: A, B, C1, C2, etc.

Return JSON:
{
  "diagrams": [
    {
      "featureName": "Complete Business Flow",
      "description": "End-to-end business process showing the complete user journey",
      "mermaidCode": "flowchart TD\\n    subgraph Init[Getting Started]\\n        A([Start]) --> B[Load Data]\\n    end"
    }
  ]
}"""

    sections_text = "\n\n".join([f"## {s.get('title', '')}\n{s.get('content', '')}" for s in documentation.get("sections", [])])
    user_prompt = f"""Generate a SINGLE comprehensive BPMN-style diagram showing the COMPLETE business flow of this application.

=== APPLICATION OVERVIEW ===
Title: {documentation.get('title', '')}
{sections_text}

=== ALL FEATURES ===
{json.dumps(analysis.get('features', []), indent=2)}

Create ONE comprehensive diagram that shows how a user progresses through the entire application workflow, from initial entry through all stages to final outputs. Use subgraphs to organize the flow by major stages/features."""

    prompt = build_prompt(system_prompt, user_prompt)
    raw_content = await call_pwc_genai(prompt)

    try:
        diagram_data = parse_json_response(raw_content)
    except Exception as parse_error:
        print(f"Failed to parse BPMN diagram JSON: {parse_error}")
        diagram_data = {"diagrams": []}

    return {
        "projectId": documentation.get("projectId", ""),
        "documentationId": documentation.get("id", ""),
        "diagrams": diagram_data.get("diagrams", []),
    }


async def transcribe_audio(audio_buffer: bytes) -> str:
    raise ValueError("Audio transcription is not currently available. Please use text input instead.")


async def generate_brd(
    feature_request: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
    knowledge_context: Optional[str],
    on_chunk: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    documentation_context = ""
    knowledge_base_context = ""
    database_schema_context = ""

    if knowledge_context:
        knowledge_base_context = f"""
=== KNOWLEDGE BASE (Relevant Documents) ===
The following information was retrieved from uploaded documents in the knowledge base.
Use this context to inform your BRD generation with domain-specific knowledge.

{knowledge_context}

=== END KNOWLEDGE BASE ===
"""

    if database_schema:
        table_descriptions = []
        for table in database_schema.get("tables", []):
            columns = []
            for col in table.get("columns", []):
                desc = f"    - {col['name']}: {col['dataType']}"
                if col.get("isPrimaryKey"):
                    desc += " (PK)"
                if col.get("isForeignKey"):
                    desc += f" (FK -> {col.get('references', '?')})"
                if not col.get("isNullable"):
                    desc += " NOT NULL"
                columns.append(desc)
            table_descriptions.append(f"  {table['name']} ({table.get('rowCount', 0):,} rows):\n" + "\n".join(columns))
        
        database_schema_context = f"""
=== CONNECTED DATABASE SCHEMA ===
Database: {database_schema.get('databaseName', '')}
Tables: {len(database_schema.get('tables', []))}

{chr(10).join(table_descriptions)}
=== END DATABASE SCHEMA ===
"""

    if documentation:
        documentation_context = f"""
=== TECHNICAL DOCUMENTATION (Generated from Repository Analysis) ===
Project: {documentation.get('title', '')}
{documentation.get('content', '')}
=== END OF DOCUMENTATION ===
"""
    elif analysis:
        documentation_context = f"""
Repository Context (from analysis):
- Architecture: {analysis.get('architecture', '')}
- Tech Stack: {json.dumps(analysis.get('techStack', {}))}
- Existing Features: {', '.join([f.get('name', '') for f in analysis.get('features', [])])}
- Testing Framework: {analysis.get('testingFramework', 'Not specified')}
"""

    system_prompt = f"""You are a senior business analyst creating a Business Requirements Document (BRD).

IMPORTANT: You are generating this BRD based on the TECHNICAL DOCUMENTATION that was generated from analyzing the repository{' AND the connected DATABASE SCHEMA' if database_schema else ''}.
Your BRD must:
1. Reference the existing components, APIs, and features from the documentation
2. Align technical considerations with the documented architecture and tech stack
3. Consider existing data models and dependencies
4. Build upon the documented features rather than reinventing them
{'5. Reference the database tables and their relationships when specifying data requirements' if database_schema else ''}

Return a JSON object with this structure:
{{
  "title": "BRD title",
  "version": "1.0",
  "status": "draft",
  "sourceDocumentation": "Title of the source documentation this BRD is based on",
  "content": {{
    "overview": "Executive summary",
    "objectives": ["List of business objectives"],
    "scope": {{"inScope": ["What's included"], "outOfScope": ["What's excluded"]}},
    "existingSystemContext": {{
      "relevantComponents": ["List existing components"],
      "relevantAPIs": ["List existing APIs"],
      "dataModelsAffected": ["List data models"]
    }},
    "functionalRequirements": [
      {{
        "id": "FR-001",
        "title": "Requirement title",
        "description": "Detailed description",
        "priority": "high|medium|low",
        "acceptanceCriteria": ["List of criteria"],
        "relatedComponents": ["Existing components this affects"]
      }}
    ],
    "nonFunctionalRequirements": [
      {{"id": "NFR-001", "category": "Performance", "description": "Description"}}
    ],
    "technicalConsiderations": ["List of technical considerations"],
    "dependencies": ["List of dependencies"],
    "assumptions": ["List of assumptions"],
    "risks": [{{"description": "Risk description", "mitigation": "Mitigation strategy"}}]
  }}
}}"""

    user_prompt = f"""Generate a comprehensive Business Requirements Document for:

Feature Request: {feature_request.get('title', '')}
Description: {feature_request.get('description', '')}
Request Type: {feature_request.get('requestType', 'feature')}

{documentation_context}
{database_schema_context}
{knowledge_base_context}"""

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_pwc_genai(prompt)

    if on_chunk:
        on_chunk(response_text)

    brd_data = parse_json_response(response_text)

    return {
        "projectId": feature_request.get("projectId", "global"),
        "featureRequestId": feature_request.get("id", ""),
        "requestType": feature_request.get("requestType", "feature"),
        "title": brd_data.get("title", feature_request.get("title", "")),
        "version": brd_data.get("version", "1.0"),
        "status": brd_data.get("status", "draft"),
        "sourceDocumentation": brd_data.get("sourceDocumentation"),
        "content": brd_data.get("content", {}),
    }


async def generate_test_cases(brd: Dict[str, Any], analysis: Optional[Dict[str, Any]], documentation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    system_prompt = """You are a QA engineer creating comprehensive test cases from a Business Requirements Document.

Generate test cases for each functional requirement. For each requirement, create test cases in these categories:
1. happy_path - Normal successful flow
2. edge_case - Boundary conditions and unusual but valid inputs
3. negative - Invalid inputs and error handling
4. e2e - End-to-end user journey tests

Return a JSON array of test cases:
[
  {
    "requirementId": "FR-001",
    "title": "Test case title",
    "description": "What this test verifies",
    "category": "happy_path|edge_case|negative|e2e",
    "type": "unit|integration|e2e|acceptance",
    "priority": "critical|high|medium|low",
    "preconditions": ["List of preconditions"],
    "steps": [{"step": 1, "action": "What to do", "expectedResult": "What should happen"}],
    "expectedOutcome": "Final expected result",
    "codeSnippet": "Optional code example"
  }
]"""

    brd_content = brd.get("content", {})
    user_prompt = f"""Generate test cases for this BRD:

Title: {brd.get('title', '')}
Overview: {brd_content.get('overview', '')}

Functional Requirements:
{json.dumps(brd_content.get('functionalRequirements', []), indent=2)}

Non-Functional Requirements:
{json.dumps(brd_content.get('nonFunctionalRequirements', []), indent=2)}"""

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_pwc_genai(prompt)
    
    test_cases = parse_json_response(response_text)
    
    return [{"brdId": brd.get("id", ""), **tc} for tc in test_cases]


async def generate_test_data(test_cases: List[Dict[str, Any]], brd: Dict[str, Any], documentation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    system_prompt = """You are a test data engineer creating realistic test data for test cases.

Generate test data sets for each test case. Include:
1. valid - Normal valid data
2. invalid - Invalid data for negative testing
3. edge - Edge case data (min/max values, empty strings, etc.)
4. boundary - Boundary condition data

IMPORTANT: Return ONLY a valid JSON array. Do NOT include any text before or after the JSON. Do NOT use markdown code fences. Ensure all string values are properly escaped (no unescaped quotes, newlines, or special characters inside strings).

Return format:
[
  {
    "testCaseId": "test case id",
    "name": "Test data name",
    "description": "What this data tests",
    "dataType": "valid|invalid|edge|boundary",
    "data": {"field1": "value1", "field2": "value2"}
  }
]"""

    tc_summaries = []
    for tc in test_cases:
        tc_summaries.append({
            "id": tc.get("id", ""),
            "title": tc.get("title", ""),
            "category": tc.get("category", ""),
            "description": tc.get("description", ""),
            "steps": tc.get("steps", []),
            "expectedOutcome": tc.get("expectedOutcome", "")
        })

    user_prompt = f"""Generate test data for these test cases:

{json.dumps(tc_summaries, indent=2)}

BRD Context:
Title: {brd.get('title', '')}
Overview: {brd.get('content', {}).get('overview', '')}"""

    prompt = build_prompt(system_prompt, user_prompt)
    
    max_retries = 2
    last_error = None
    for attempt in range(max_retries):
        try:
            response_text = await call_pwc_genai(prompt)
            result = parse_json_response(response_text)
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return [result]
            else:
                raise ValueError(f"Unexpected response type: {type(result)}")
        except Exception as e:
            last_error = e
            print(f"Test data generation attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print("Retrying...")
    
    raise last_error


async def generate_user_stories(
    brd: Dict[str, Any],
    documentation: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
    parent_context: Optional[str],
    knowledge_context: Optional[str]
) -> List[Dict[str, Any]]:
    system_prompt = """You are a product owner creating JIRA-style user stories from a Business Requirements Document.

Generate user stories following this format:
- As a [role], I want [feature], so that [benefit]
- Include detailed acceptance criteria
- Add story points estimate (1, 2, 3, 5, 8, 13)
- Include relevant labels

Return a JSON array of user stories:
[
  {
    "storyKey": "US-001",
    "title": "User story title",
    "description": "Detailed description",
    "asA": "role",
    "iWant": "feature",
    "soThat": "benefit",
    "acceptanceCriteria": ["AC1", "AC2"],
    "priority": "highest|high|medium|low|lowest",
    "storyPoints": 5,
    "labels": ["label1", "label2"],
    "epic": "Epic name if applicable",
    "relatedRequirementId": "FR-001",
    "technicalNotes": "Implementation notes",
    "dependencies": ["Other story dependencies"]
  }
]"""

    brd_content = brd.get("content", {})
    context_parts = []
    if parent_context:
        context_parts.append(f"Parent Story Context:\n{parent_context}")
    if knowledge_context:
        context_parts.append(f"Knowledge Base Context:\n{knowledge_context}")
    if database_schema:
        context_parts.append(f"Database Schema: {database_schema.get('databaseName', '')} with {len(database_schema.get('tables', []))} tables")

    user_prompt = f"""Generate user stories for this BRD:

Title: {brd.get('title', '')}
Overview: {brd_content.get('overview', '')}
Request Type: {brd.get('requestType', 'feature')}

Functional Requirements:
{json.dumps(brd_content.get('functionalRequirements', []), indent=2)}

{chr(10).join(context_parts)}"""

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_pwc_genai(prompt)
    
    stories = parse_json_response(response_text)
    
    return [{"brdId": brd.get("id", ""), **story} for story in stories]


async def generate_copilot_prompt(
    user_stories: List[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
    feature_request: Optional[Dict[str, Any]] = None
) -> str:
    system_prompt = """You are an expert prompt engineer creating a highly detailed, implementation-ready VS Code Copilot prompt. The prompt you generate will be used by a developer to implement specific user stories in an existing codebase.

Your generated prompt MUST include ALL of the following sections with rich detail:

## 1. PROJECT CONTEXT
- Repository name, description, and purpose
- Full architecture overview (frontend, backend, API design, data flow)
- Complete tech stack with versions where available
- Existing code patterns and conventions the developer must follow

## 2. REPOSITORY STRUCTURE
- Directory layout and file organization
- Key files and their responsibilities
- Module boundaries and dependencies

## 3. TASK BREAKDOWN (Most Important Section)
For EACH user story, create an elaborate implementation task that includes:
- **What to build**: Detailed functional description
- **Where to implement**: Exact files to create or modify, with file paths
- **How to implement**: Step-by-step implementation approach
- **Data models**: Any new or modified data structures/schemas needed
- **API endpoints**: New routes, request/response schemas, HTTP methods
- **UI components**: Frontend components to create or modify
- **Business logic**: Core logic, validation rules, edge cases to handle
- **Integration points**: How this connects to existing code
- **Acceptance criteria**: Specific conditions that must be met

## 4. TECHNICAL CONSTRAINTS
- Code style and naming conventions from the existing codebase
- Framework-specific patterns to follow
- Error handling approach
- Security considerations

## 5. TESTING REQUIREMENTS
- Unit tests needed
- Integration test scenarios
- Edge cases to test

## 6. DATABASE CHANGES (if applicable)
- New tables/columns needed
- Migration scripts
- Relationships and constraints

Make the prompt comprehensive enough that a developer can implement each story without needing additional context. Be specific about file paths, function names, and code patterns from the existing codebase."""

    stories_detail = []
    for i, s in enumerate(user_stories, 1):
        story_text = f"""### Story {i}: {s.get('storyKey', 'N/A')} - {s.get('title', 'Untitled')}
- **Priority**: {s.get('priority', 'Medium')}
- **Story Points**: {s.get('storyPoints', 0)}
- **Description**: {s.get('description', 'No description')}
- **Acceptance Criteria**: {s.get('acceptanceCriteria', 'None specified')}"""
        if s.get('technicalNotes'):
            story_text += f"\n- **Technical Notes**: {s['technicalNotes']}"
        if s.get('dependencies'):
            story_text += f"\n- **Dependencies**: {s['dependencies']}"
        stories_detail.append(story_text)

    context_sections = []

    if analysis:
        arch_section = "## REPOSITORY ANALYSIS\n"
        if analysis.get('summary'):
            arch_section += f"**Summary**: {analysis['summary']}\n\n"
        if analysis.get('architecture'):
            arch_section += f"**Architecture**: {analysis['architecture']}\n\n"

        tech_stack = analysis.get('techStack', {})
        if tech_stack:
            arch_section += "**Tech Stack**:\n"
            if tech_stack.get('languages'):
                arch_section += f"- Languages: {', '.join(tech_stack['languages'])}\n"
            if tech_stack.get('frameworks'):
                arch_section += f"- Frameworks: {', '.join(tech_stack['frameworks'])}\n"
            if tech_stack.get('databases'):
                arch_section += f"- Databases: {', '.join(tech_stack['databases'])}\n"
            if tech_stack.get('tools'):
                arch_section += f"- Tools: {', '.join(tech_stack['tools'])}\n"
            arch_section += "\n"

        if analysis.get('codePatterns'):
            arch_section += "**Existing Code Patterns**:\n"
            for pattern in analysis['codePatterns']:
                arch_section += f"- {pattern}\n"
            arch_section += "\n"

        if analysis.get('testingFramework'):
            arch_section += f"**Testing Framework**: {analysis['testingFramework']}\n\n"

        features = analysis.get('features', [])
        if features:
            arch_section += "**Existing Features & Related Files**:\n"
            for feat in features:
                arch_section += f"- **{feat.get('name', '')}**: {feat.get('description', '')}\n"
                if feat.get('files'):
                    arch_section += f"  Files: {', '.join(feat['files'])}\n"
            arch_section += "\n"

        context_sections.append(arch_section)

    if documentation:
        doc_section = "## DOCUMENTATION\n"
        if documentation.get('title'):
            doc_section += f"**Project**: {documentation['title']}\n\n"
        if documentation.get('content'):
            content = documentation['content']
            if len(content) > 4000:
                content = content[:4000] + "\n... (truncated for brevity)"
            doc_section += f"**Technical Documentation**:\n{content}\n\n"
        if documentation.get('sections'):
            doc_section += "**Documentation Sections**:\n"
            for sec in documentation.get('sections', []):
                if isinstance(sec, dict):
                    doc_section += f"- {sec.get('title', '')}: {sec.get('content', '')[:200]}\n"
                elif isinstance(sec, str):
                    doc_section += f"- {sec[:200]}\n"
            doc_section += "\n"
        context_sections.append(doc_section)

    if database_schema:
        db_section = "## DATABASE SCHEMA\n"
        db_section += f"**Database**: {database_schema.get('databaseName', 'Unknown')}\n"
        db_section += f"**Connection**: {database_schema.get('connectionString', 'N/A')}\n\n"
        tables = database_schema.get('tables', [])
        if tables:
            db_section += f"**Tables ({len(tables)})**:\n"
            for table in tables:
                db_section += f"\n### Table: `{table.get('name', '')}`"
                if table.get('rowCount') is not None:
                    db_section += f" ({table['rowCount']} rows)"
                db_section += "\n"
                columns = table.get('columns', [])
                if columns:
                    db_section += "| Column | Type | Nullable | PK | FK |\n"
                    db_section += "|--------|------|----------|----|----|" + "\n"
                    for col in columns:
                        pk = "Yes" if col.get('isPrimaryKey') else ""
                        fk = col.get('foreignKeyRef', '') if col.get('isForeignKey') else ""
                        db_section += f"| `{col.get('name', '')}` | {col.get('dataType', '')} | {col.get('isNullable', False)} | {pk} | {fk} |\n"
            db_section += "\n"
        context_sections.append(db_section)

    if feature_request:
        req_section = "## FEATURE REQUEST CONTEXT\n"
        if feature_request.get('title'):
            req_section += f"**Title**: {feature_request['title']}\n"
        if feature_request.get('description'):
            req_section += f"**Description**: {feature_request['description']}\n"
        if feature_request.get('requestType'):
            req_section += f"**Request Type**: {feature_request['requestType']}\n"
        req_section += "\n"
        context_sections.append(req_section)

    user_prompt = f"""Generate a comprehensive, implementation-ready VS Code Copilot prompt for the following user stories.

Include the FULL repository context, architecture details, file structure, and code patterns so the developer has everything needed for accurate code generation.

For each user story, elaborate the TASK extensively - specify exact files to modify/create, function signatures, data models, API routes, UI components, validation logic, and step-by-step implementation instructions.

---

# USER STORIES TO IMPLEMENT

{chr(10).join(stories_detail)}

---

# CODEBASE CONTEXT

{chr(10).join(context_sections)}

---

Generate the Copilot prompt now. Make the Task section for each story extremely detailed with specific file paths, code patterns to follow, and implementation steps. The prompt should be self-contained so a developer can implement everything without needing to ask questions."""

    prompt = build_prompt(system_prompt, user_prompt)
    return await call_pwc_genai(prompt)


async def find_related_stories(feature_description: str, jira_stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    system_prompt = """You are analyzing JIRA stories to find ones semantically related to a new feature request.

Return a JSON array of related story objects. Include only stories that are genuinely related.
Score each story from 0.0 to 1.0 based on relevance.

Return format:
[
  {"key": "PROJ-123", "summary": "Story summary", "relevanceScore": 0.85, "reason": "Why it's related"}
]

If no stories are related, return an empty array: []"""

    stories_text = "\n".join([
        f"- {s.get('key', '')}: {s.get('summary', '')} [{s.get('issueType', 'Story')}]"
        for s in jira_stories
    ])

    user_prompt = f"""Find JIRA stories related to this feature:

Feature Description:
{feature_description}

Available JIRA Stories:
{stories_text}"""

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_pwc_genai(prompt)
    
    try:
        related = parse_json_response(response_text)
        return related if isinstance(related, list) else []
    except:
        return []
