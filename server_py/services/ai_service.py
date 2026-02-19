"""AI service for GenAI interactions and document generation."""
import os
import re
import json
import base64
import httpx
from typing import Optional, Callable, Dict, Any, List
from core.config import get_settings
from core.logging import log_info, log_error, log_debug
from utils.text import parse_json_response
from utils.pwc_llm import call_pwc_genai_async, build_pwc_prompt
from prompts import prompt_loader


class AIService:
    """Service for AI/GenAI operations and document generation."""
    
    def __init__(self):
        self.settings = get_settings()
        
    async def call_genai(
        self, 
        prompt: str, 
        temperature: float = 0.2, 
        max_tokens: int = 6096
    ) -> str:
        """Call PwC GenAI API using centralized utility."""
        log_info(f"Calling PwC GenAI (prompt length: {len(prompt)} chars)", "ai")
        log_debug(f"AI parameters: temp={temperature}, max_tokens={max_tokens}", "ai")
        log_debug(f"Using model: vertex_ai.gemini-2.0-flash", "ai")
        
        try:
            response = await call_pwc_genai_async(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120
            )
            log_info("PwC GenAI response received successfully", "ai")
            return response
        except Exception as e:
            error_msg = f"PwC GenAI API Error: {str(e)}"
            log_error(error_msg, "ai")
            raise
    
    def build_prompt(self, system_message: str, user_message: str) -> str:
        """Build a formatted prompt."""
        return build_pwc_prompt(system_message, user_message)

    def _get_github_headers(self) -> Dict[str, str]:
        """Get GitHub API headers with optional authentication."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DocuGen-AI",
        }
        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def fetch_repo_contents(self, repo_url: str) -> str:
        """Fetch repository contents from GitHub."""
        match = re.match(r"github\.com/([^/]+)/([^/]+)", repo_url.replace("https://", ""))
        if not match:
            raise ValueError("Invalid GitHub URL")

        owner = match.group(1)
        repo = match.group(2).replace(".git", "")
        headers = self._get_github_headers()

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
                log_error(f"Error fetching {file_path}", "ai", e)
            return None

        import asyncio
        for i in range(0, len(files_to_fetch), 10):
            if total_chars >= max_total_chars:
                break
            batch = files_to_fetch[i:i+10]
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

        log_info(f"Fetched {len(file_contents)} files, {total_chars} total characters for {owner}/{repo}", "ai")

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

    async def analyze_repository(self, repo_url: str, project_id: str) -> Dict[str, Any]:
        """Analyze a GitHub repository and extract key information."""
        repo_context = await self.fetch_repo_contents(repo_url)

        system_prompt = prompt_loader.get_prompt("ai_service.yml", "analyze_repository_system")
        user_prompt = prompt_loader.get_prompt("ai_service.yml", "analyze_repository_user").format(
            repo_context=repo_context
        )
        
        prompt = self.build_prompt(system_prompt, user_prompt)
        response_text = await self.call_genai(prompt)
        
        analysis_data = parse_json_response(response_text)
        
        return {
            **analysis_data,
            "projectId": project_id,
        }

    async def generate_documentation(self, analysis: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
        """Generate technical documentation for a project."""
        repo_context = ""
        try:
            repo_context = await self.fetch_repo_contents(project["repoUrl"])
            log_info(f"Documentation: Re-fetched repo contents for {project['name']}", "ai")
        except Exception as err:
            log_error(f"Failed to fetch repo for documentation", "ai", err)

        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_documentation_system")

        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_documentation_user").format(
            repo_context=repo_context,
            project_name=project['name'],
            features_list=json.dumps(analysis.get('features', []), indent=2),
            tech_stack=json.dumps(analysis.get('techStack', {}), indent=2)
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        raw_content = await self.call_genai(prompt)

        try:
            doc_data = parse_json_response(raw_content)
        except Exception as parse_error:
            log_error("Failed to parse documentation JSON", "ai", parse_error)
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

    async def generate_bpmn_diagram(self, documentation: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate BPMN diagrams from documentation."""
        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_bpmn_diagram_system")

        sections_text = "\n\n".join([f"## {s.get('title', '')}\n{s.get('content', '')}" for s in documentation.get("sections", [])])
        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_bpmn_diagram_user").format(
            documentation_title=documentation.get('title', ''),
            sections_text=sections_text,
            features_json=json.dumps(analysis.get('features', []), indent=2)
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        raw_content = await self.call_genai(prompt)

        try:
            diagram_data = parse_json_response(raw_content)
        except Exception as parse_error:
            log_error("Failed to parse BPMN diagram JSON", "ai", parse_error)
            diagram_data = {"diagrams": []}

        return {
            "projectId": documentation.get("projectId", ""),
            "documentationId": documentation.get("id", ""),
            "diagrams": diagram_data.get("diagrams", []),
        }

    async def transcribe_audio(self, audio_buffer: bytes) -> str:
        """Transcribe audio to text (currently not available)."""
        raise ValueError("Audio transcription is not currently available. Please use text input instead.")

    async def generate_brd(
        self,
        feature_request: Dict[str, Any],
        analysis: Optional[Dict[str, Any]],
        documentation: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """Generate Business Requirements Document with comprehensive context."""
        from core.logging import log_info, log_warning
        
        documentation_context = ""
        knowledge_base_context = ""
        database_schema_context = ""
        
        # Log context availability for debugging
        log_info(f"BRD Generation Context - KB: {bool(knowledge_context)}, Docs: {bool(documentation)}, DB: {bool(database_schema)}, Analysis: {bool(analysis)}", "ai_service")

        # PRIORITY 1: Knowledge Base Context (Retrieved specifically for this feature request)
        if knowledge_context:
            context_size = len(knowledge_context)
            log_info(f"Using Knowledge Base context ({context_size} chars) retrieved for: {feature_request.get('title', 'N/A')}", "ai_service")
            knowledge_base_context = f"""
=== KNOWLEDGE BASE (Retrieved Documents - PRIMARY CONTEXT) ===
IMPORTANT: The following information was specifically retrieved from uploaded documents based on this feature request.
This is domain-specific knowledge that should guide your BRD generation.
Length: {context_size} characters

{knowledge_context}

=== END KNOWLEDGE BASE ===
"""
        else:
            log_warning("No Knowledge Base context available for BRD generation", "ai_service")

        # PRIORITY 2: Database Schema Context
        if database_schema:
            table_count = len(database_schema.get("tables", []))
            log_info(f"Using Database Schema with {table_count} tables", "ai_service")
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
Tables: {table_count}

{chr(10).join(table_descriptions)}
=== END DATABASE SCHEMA ===
"""
        else:
            log_info("No Database Schema available", "ai_service")

        # PRIORITY 3: Technical Documentation Context
        if documentation:
            doc_title = documentation.get('title', 'N/A')
            log_info(f"Using Technical Documentation: {doc_title}", "ai_service")
            documentation_context = f"""
=== TECHNICAL DOCUMENTATION (Generated from Repository Analysis) ===
Project: {documentation.get('title', '')}
{documentation.get('content', '')}
=== END OF DOCUMENTATION ===
"""
        elif analysis:
            log_info("Using Repository Analysis (fallback from documentation)", "ai_service")
            documentation_context = f"""
=== REPOSITORY CONTEXT (from analysis) ===
- Architecture: {analysis.get('architecture', '')}
- Tech Stack: {json.dumps(analysis.get('techStack', {}))}
- Existing Features: {', '.join([f.get('name', '') for f in analysis.get('features', [])])}
- Testing Framework: {analysis.get('testingFramework', 'Not specified')}
=== END REPOSITORY CONTEXT ===
"""
        else:
            log_warning("No Documentation or Analysis context available", "ai_service")

        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_brd_system").format(
            database_schema_note=' AND the connected DATABASE SCHEMA' if database_schema else '',
            database_schema_requirement='5. Reference the database tables and their relationships when specifying data requirements' if database_schema else ''
        )

        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_brd_user").format(
            feature_title=feature_request.get('title', ''),
            feature_description=feature_request.get('description', ''),
            request_type=feature_request.get('requestType', 'feature'),
            documentation_context=documentation_context,
            database_schema_context=database_schema_context,
            knowledge_base_context=knowledge_base_context
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        response_text = await self.call_genai(prompt)

        if on_chunk:
            on_chunk(response_text)

        brd_data = parse_json_response(response_text)
        
        from datetime import datetime
        timestamp = datetime.utcnow().isoformat()

        return {
            "projectId": feature_request.get("projectId", "global"),
            "featureRequestId": feature_request.get("id", ""),
            "requestType": feature_request.get("requestType", "feature"),
            "title": brd_data.get("title", feature_request.get("title", "")),
            "version": brd_data.get("version", "1.0"),
            "status": brd_data.get("status", "draft"),
            "sourceDocumentation": brd_data.get("sourceDocumentation"),
            "content": brd_data.get("content", {}),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

    async def generate_test_cases(self, brd: Dict[str, Any], analysis: Optional[Dict[str, Any]], documentation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate test cases from BRD."""
        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_test_cases_system")

        brd_content = brd.get("content", {})
        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_test_cases_user").format(
            brd_title=brd.get('title', ''),
            brd_overview=brd_content.get('overview', ''),
            functional_requirements_json=json.dumps(brd_content.get('functionalRequirements', []), indent=2),
            non_functional_requirements_json=json.dumps(brd_content.get('nonFunctionalRequirements', []), indent=2)
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        response_text = await self.call_genai(prompt)
        
        test_cases = parse_json_response(response_text)
        
        return [{"brdId": brd.get("id", ""), **tc} for tc in test_cases]

    async def generate_test_data(self, test_cases: List[Dict[str, Any]], brd: Dict[str, Any], documentation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate test data for test cases."""
        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_test_data_system")

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

        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_test_data_user").format(
            test_cases_json=json.dumps(tc_summaries, indent=2)
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        
        max_retries = 2
        last_error = None
        for attempt in range(max_retries):
            try:
                response_text = await self.call_genai(prompt)
                result = parse_json_response(response_text)
                if isinstance(result, list):
                    return result
                elif isinstance(result, dict):
                    return [result]
                else:
                    raise ValueError(f"Unexpected response type: {type(result)}")
            except Exception as e:
                last_error = e
                log_error(f"Test data generation attempt {attempt + 1} failed", "ai", e)
                if attempt < max_retries - 1:
                    log_info("Retrying test data generation...", "ai")
        
        raise last_error

    async def generate_user_stories(
        self,
        brd: Dict[str, Any],
        documentation: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        parent_context: Optional[str],
        knowledge_context: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Generate user stories from BRD."""
        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_user_stories_system")

        brd_content = brd.get("content", {})
        context_parts = []
        if parent_context:
            context_parts.append(f"Parent Story Context:\n{parent_context}")
        if knowledge_context:
            context_parts.append(f"Knowledge Base Context:\n{knowledge_context}")
        if database_schema:
            context_parts.append(f"Database Schema: {database_schema.get('databaseName', '')} with {len(database_schema.get('tables', []))} tables")

        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_user_stories_user").format(
            brd_title=brd.get('title', ''),
            brd_overview=brd_content.get('overview', ''),
            request_type=brd.get('requestType', 'feature'),
            functional_requirements_json=json.dumps(brd_content.get('functionalRequirements', []), indent=2),
            context_parts=chr(10).join(context_parts)
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        response_text = await self.call_genai(prompt)
        
        stories = parse_json_response(response_text)
        
        return [{"brdId": brd.get("id", ""), **story} for story in stories]

    async def generate_copilot_prompt(
        self,
        user_stories: List[Dict[str, Any]],
        documentation: Optional[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        feature_request: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a detailed GitHub Copilot prompt."""
        system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_copilot_prompt_system")

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

        user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_copilot_prompt_user").format(
            stories_detail=chr(10).join(stories_detail),
            context_sections=chr(10).join(context_sections)
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        return await self.call_genai(prompt)

    async def find_related_stories(self, feature_description: str, jira_stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find related JIRA stories based on feature description."""
        system_prompt = prompt_loader.get_prompt("ai_service.yml", "find_related_stories_system")

        stories_text = "\n".join([
            f"- {s.get('key', '')}: {s.get('summary', '')} [{s.get('issueType', 'Story')}]"
            for s in jira_stories
        ])

        user_prompt = prompt_loader.get_prompt("ai_service.yml", "find_related_stories_user").format(
            feature_description=feature_description,
            stories_text=stories_text
        )

        prompt = self.build_prompt(system_prompt, user_prompt)
        response_text = await self.call_genai(prompt)
        
        try:
            related = parse_json_response(response_text)
            return related if isinstance(related, list) else []
        except:
            return []


# Global AI service instance
ai_service = AIService()
