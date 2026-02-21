"""AI generation functions for documents, test cases, and related artifacts."""
import json
from typing import Optional, Callable, Dict, Any, List, Awaitable, AsyncIterator
from core.logging import log_info, log_error, log_warning
from utils.text import parse_json_response
from prompts import prompt_loader


CallGenAI = Callable[[str, float, int], Awaitable[str]]
StreamGenAI = Callable[..., AsyncIterator[str]]
BuildPrompt = Callable[[str, str], str]


async def generate_documentation(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    analysis: Dict[str, Any],
    project: Dict[str, Any],
    fetch_repo_contents_fn: Callable
) -> Dict[str, Any]:
    """Generate technical documentation for a project."""
    repo_context = ""
    try:
        repo_context = await fetch_repo_contents_fn(project["repoUrl"])
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

    prompt = build_prompt(system_prompt, user_prompt)
    raw_content = await call_genai(prompt)

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


async def generate_bpmn_diagram(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    documentation: Dict[str, Any],
    analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate BPMN diagrams from documentation."""
    system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_bpmn_diagram_system")

    sections_text = "\n\n".join([f"## {s.get('title', '')}\n{s.get('content', '')}" for s in documentation.get("sections", [])])
    user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_bpmn_diagram_user").format(
        documentation_title=documentation.get('title', ''),
        sections_text=sections_text,
        features_json=json.dumps(analysis.get('features', []), indent=2)
    )

    prompt = build_prompt(system_prompt, user_prompt)
    raw_content = await call_genai(prompt)

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


async def generate_brd(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    feature_request: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
    knowledge_context: Optional[str],
    on_chunk: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """Generate Business Requirements Document with comprehensive context."""
    documentation_context = ""
    knowledge_base_context = ""
    database_schema_context = ""
    
    log_info(f"BRD Generation Context - KB: {bool(knowledge_context)}, Docs: {bool(documentation)}, DB: {bool(database_schema)}, Analysis: {bool(analysis)}", "ai_service")

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

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_genai(prompt)

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


async def generate_brd_streaming(
    stream_genai: StreamGenAI,
    build_prompt: BuildPrompt,
    feature_request: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
    knowledge_context: Optional[str],
    on_chunk: Optional[Callable[[str], None]] = None,
):
    """Generate BRD with true streaming — yields text chunks as they arrive.

    This is an async generator.  It yields each text delta from the LLM so that
    the API layer can push them to the client over SSE in real-time.

    At the end it yields a final dict (the complete BRD object) so the caller
    knows the generation is done and can persist it.
    """
    documentation_context = ""
    knowledge_base_context = ""
    database_schema_context = ""

    log_info(
        f"BRD Streaming Generation Context - KB: {bool(knowledge_context)}, "
        f"Docs: {bool(documentation)}, DB: {bool(database_schema)}, "
        f"Analysis: {bool(analysis)}",
        "ai_service",
    )

    if knowledge_context:
        context_size = len(knowledge_context)
        log_info(
            f"Using Knowledge Base context ({context_size} chars) for: "
            f"{feature_request.get('title', 'N/A')}",
            "ai_service",
        )
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
            table_descriptions.append(
                f"  {table['name']} ({table.get('rowCount', 0):,} rows):\n" + "\n".join(columns)
            )
        database_schema_context = f"""
=== CONNECTED DATABASE SCHEMA ===
Database: {database_schema.get('databaseName', '')}
Tables: {table_count}

{chr(10).join(table_descriptions)}
=== END DATABASE SCHEMA ===
"""
    else:
        log_info("No Database Schema available", "ai_service")

    if documentation:
        doc_title = documentation.get("title", "N/A")
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
        database_schema_note=" AND the connected DATABASE SCHEMA" if database_schema else "",
        database_schema_requirement=(
            "5. Reference the database tables and their relationships when specifying data requirements"
            if database_schema
            else ""
        ),
    )

    user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_brd_user").format(
        feature_title=feature_request.get("title", ""),
        feature_description=feature_request.get("description", ""),
        request_type=feature_request.get("requestType", "feature"),
        documentation_context=documentation_context,
        database_schema_context=database_schema_context,
        knowledge_base_context=knowledge_base_context,
    )

    prompt = build_prompt(system_prompt, user_prompt)

    accumulated = ""
    async for chunk in stream_genai(prompt=prompt, task_name="generate_brd"):
        accumulated += chunk
        if on_chunk:
            on_chunk(chunk)
        yield {"type": "chunk", "text": chunk}

    brd_data = parse_json_response(accumulated)

    from datetime import datetime

    timestamp = datetime.utcnow().isoformat()

    brd = {
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

    yield {"type": "done", "brd": brd}


# ==================== PARALLEL BRD SECTION GENERATION ====================

EXISTING_SYSTEM_SECTION = {
    "key": "existingSystemContext",
    "task_name": "brd_section_existing_system",
    "prompt_key": "brd_section_existing_system_prompt",
}

PARALLEL_SECTIONS = [
    {
        "key": "overview",
        "task_name": "brd_section_overview",
        "prompt_key": "brd_section_overview_prompt",
    },
    {
        "key": "objectives",
        "task_name": "brd_section_objectives",
        "prompt_key": "brd_section_objectives_prompt",
    },
    {
        "key": "scope",
        "task_name": "brd_section_scope",
        "prompt_key": "brd_section_scope_prompt",
    },
    {
        "key": "functionalRequirements",
        "task_name": "brd_section_functional_req",
        "prompt_key": "brd_section_functional_req_prompt",
    },
    {
        "key": "nonFunctionalRequirements",
        "task_name": "brd_section_nonfunctional_req",
        "prompt_key": "brd_section_nonfunctional_req_prompt",
    },
    {
        "key": "technical",
        "task_name": "brd_section_technical",
        "prompt_key": "brd_section_technical_prompt",
    },
    {
        "key": "risks",
        "task_name": "brd_section_risks",
        "prompt_key": "brd_section_risks_prompt",
    },
    {
        "key": "meta",
        "task_name": "brd_section_meta",
        "prompt_key": "brd_section_meta_prompt",
    },
]


async def _generate_single_section(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    section_cfg: Dict[str, Any],
    format_vars: Dict[str, str],
) -> Dict[str, Any]:
    """Generate a single BRD section via its own LLM call."""
    import asyncio

    section_key = section_cfg["key"]
    task_name = section_cfg["task_name"]

    system_prompt = prompt_loader.get_prompt("ai_service.yml", "brd_section_base_context").format(
        database_schema_note=format_vars.get("database_schema_note", ""),
    )

    user_prompt_template = prompt_loader.get_prompt("ai_service.yml", section_cfg["prompt_key"])

    safe_vars = {k: format_vars.get(k, "") for k in [
        "feature_title", "feature_description", "request_type",
        "knowledge_base_context", "documentation_context", "database_schema_context",
        "existing_system_context",
    ]}
    user_prompt = user_prompt_template.format(**safe_vars)

    prompt = build_prompt(system_prompt, user_prompt)

    log_info(f"BRD section '{section_key}' — calling LLM (task: {task_name})", "generators")
    start = asyncio.get_event_loop().time()

    raw = await call_genai(prompt)

    elapsed = asyncio.get_event_loop().time() - start
    log_info(f"BRD section '{section_key}' — completed in {elapsed:.1f}s", "generators")

    try:
        data = parse_json_response(raw)
    except Exception as e:
        log_error(f"Failed to parse section '{section_key}' JSON", "generators", e)
        data = {}

    return {"section": section_key, "data": data}


async def generate_brd_parallel(
    call_genai_factory: Callable[[str], CallGenAI],
    build_prompt: BuildPrompt,
    feature_request: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
    knowledge_context: Optional[str],
):
    """Generate BRD with 9 parallel independent LLM calls, yielding sections as they complete.

    This is an async generator. It yields section events:
        {"type": "section", "section": "<key>", "data": {...}}
    and finally:
        {"type": "done", "brd": {...}}
    """
    import asyncio

    documentation_context = ""
    knowledge_base_context = ""
    database_schema_context = ""

    log_info(
        f"BRD Parallel Generation — KB: {bool(knowledge_context)}, "
        f"Docs: {bool(documentation)}, DB: {bool(database_schema)}, "
        f"Analysis: {bool(analysis)}",
        "ai_service",
    )

    if knowledge_context:
        log_info(f"Using KB context ({len(knowledge_context)} chars)", "ai_service")
        knowledge_base_context = f"""
=== KNOWLEDGE BASE (Retrieved Documents - PRIMARY CONTEXT) ===
{knowledge_context}
=== END KNOWLEDGE BASE ===
"""

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
                columns.append(desc)
            table_descriptions.append(
                f"  {table['name']}:\n" + "\n".join(columns)
            )
        database_schema_context = f"""
=== DATABASE SCHEMA ===
{chr(10).join(table_descriptions)}
=== END DATABASE SCHEMA ===
"""

    if documentation:
        doc_title = documentation.get("title", "N/A")
        log_info(f"Using Documentation: {doc_title}", "ai_service")
        documentation_context = f"""
=== TECHNICAL DOCUMENTATION ===
Project: {documentation.get('title', '')}
{documentation.get('content', '')}
=== END DOCUMENTATION ===
"""
    elif analysis:
        documentation_context = f"""
=== REPOSITORY CONTEXT ===
Architecture: {analysis.get('architecture', '')}
Tech Stack: {json.dumps(analysis.get('techStack', {}))}
Features: {', '.join([f.get('name', '') for f in analysis.get('features', [])])}
=== END REPOSITORY CONTEXT ===
"""

    format_vars = {
        "feature_title": feature_request.get("title", ""),
        "feature_description": feature_request.get("description", ""),
        "request_type": feature_request.get("requestType", "feature"),
        "knowledge_base_context": knowledge_base_context,
        "documentation_context": documentation_context,
        "database_schema_context": database_schema_context,
        "database_schema_note": " AND the connected DATABASE SCHEMA" if database_schema else "",
        "existing_system_context": "",
    }

    total = 1 + len(PARALLEL_SECTIONS)
    completed_count = 0

    log_info("Phase 1: Generating Existing System Context (sequential)...", "generators")
    existing_system_data = {}
    try:
        caller = call_genai_factory(EXISTING_SYSTEM_SECTION["task_name"])
        result = await _generate_single_section(caller, build_prompt, EXISTING_SYSTEM_SECTION, format_vars)
        existing_system_data = result["data"]
        completed_count += 1
        log_info(f"BRD section 'existingSystemContext' ready ({completed_count}/{total})", "generators")
        yield {"type": "section", "section": "existingSystemContext", "data": existing_system_data, "progress": completed_count, "total": total}
    except Exception as esc_err:
        log_error("BRD section 'existingSystemContext' failed", "generators", esc_err)
        completed_count += 1
        yield {"type": "section", "section": "existingSystemContext", "data": {}, "progress": completed_count, "total": total}

    existing_system_context_text = ""
    if existing_system_data:
        parts = []
        if existing_system_data.get("relevantComponents"):
            parts.append(f"Relevant Components: {', '.join(existing_system_data['relevantComponents'])}")
        if existing_system_data.get("relevantAPIs"):
            parts.append(f"Relevant APIs: {', '.join(existing_system_data['relevantAPIs'])}")
        if existing_system_data.get("dataModelsAffected"):
            parts.append(f"Data Models Affected: {', '.join(existing_system_data['dataModelsAffected'])}")
        if existing_system_data.get("architectureNotes"):
            parts.append(f"Architecture Notes: {existing_system_data['architectureNotes']}")
        if existing_system_data.get("implementationApproach"):
            parts.append(f"Implementation Approach: {existing_system_data['implementationApproach']}")
        if existing_system_data.get("reusableCode"):
            parts.append(f"Reusable Code: {', '.join(existing_system_data['reusableCode'])}")
        existing_system_context_text = f"""
=== EXISTING SYSTEM CONTEXT (Codebase Analysis) ===
{chr(10).join(parts)}
=== END EXISTING SYSTEM CONTEXT ===
"""

    format_vars["existing_system_context"] = existing_system_context_text

    log_info(
        f"Phase 2: Generating {len(PARALLEL_SECTIONS)} sections in parallel — "
        f"existing_system_ctx: {len(existing_system_context_text)} chars, "
        f"docs: {len(documentation_context)} chars, "
        f"kb: {len(knowledge_base_context)} chars, "
        f"db_schema: {len(database_schema_context)} chars",
        "generators",
    )

    async def _run_section(cfg):
        caller = call_genai_factory(cfg["task_name"])
        return await _generate_single_section(caller, build_prompt, cfg, format_vars)

    tasks = {
        asyncio.create_task(_run_section(cfg)): cfg["key"]
        for cfg in PARALLEL_SECTIONS
    }

    content = {}
    meta = {}

    for coro in asyncio.as_completed(tasks.keys()):
        try:
            result = await coro
            section_key = result["section"]
            section_data = result["data"]
            completed_count += 1

            if section_key == "meta":
                meta = section_data
            elif section_key == "technical":
                content["technicalConsiderations"] = section_data.get("technicalConsiderations", [])
                content["dependencies"] = section_data.get("dependencies", [])
                content["assumptions"] = section_data.get("assumptions", [])
            elif section_key == "scope":
                content["scope"] = section_data.get("scope", {"inScope": [], "outOfScope": []})
            elif section_key == "overview":
                content["overview"] = section_data.get("overview", "")
            elif section_key == "objectives":
                content["objectives"] = section_data.get("objectives", [])
            else:
                content[section_key] = section_data.get(section_key, section_data)

            log_info(f"BRD section '{section_key}' ready ({completed_count}/{total})", "generators")
            yield {"type": "section", "section": section_key, "data": section_data, "progress": completed_count, "total": total}

        except Exception as section_err:
            section_key = "unknown"
            for t, k in tasks.items():
                if t.done():
                    try:
                        t.result()
                    except:
                        section_key = k
                        break
            log_error(f"BRD section '{section_key}' failed", "generators", section_err)
            completed_count += 1
            yield {"type": "section", "section": section_key, "data": {}, "progress": completed_count, "total": total}

    content["existingSystemContext"] = existing_system_data

    from datetime import datetime
    timestamp = datetime.utcnow().isoformat()

    brd = {
        "projectId": feature_request.get("projectId", "global"),
        "featureRequestId": feature_request.get("id", ""),
        "requestType": feature_request.get("requestType", "feature"),
        "title": meta.get("title", feature_request.get("title", "")),
        "version": meta.get("version", "1.0"),
        "status": meta.get("status", "draft"),
        "sourceDocumentation": meta.get("sourceDocumentation"),
        "content": content,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }

    yield {"type": "done", "brd": brd}


async def generate_test_cases(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    brd: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Generate test cases from BRD."""
    system_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_test_cases_system")

    brd_content = brd.get("content", {})
    user_prompt = prompt_loader.get_prompt("ai_service.yml", "generate_test_cases_user").format(
        brd_title=brd.get('title', ''),
        brd_overview=brd_content.get('overview', ''),
        functional_requirements_json=json.dumps(brd_content.get('functionalRequirements', []), indent=2),
        non_functional_requirements_json=json.dumps(brd_content.get('nonFunctionalRequirements', []), indent=2)
    )

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_genai(prompt)
    
    test_cases = parse_json_response(response_text)
    
    return [{"brdId": brd.get("id", ""), **tc} for tc in test_cases]


async def generate_test_data(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    test_cases: List[Dict[str, Any]],
    brd: Dict[str, Any],
    documentation: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
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

    prompt = build_prompt(system_prompt, user_prompt)
    
    max_retries = 2
    last_error = None
    for attempt in range(max_retries):
        try:
            response_text = await call_genai(prompt)
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
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
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

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_genai(prompt)
    
    stories = parse_json_response(response_text)
    
    return [{"brdId": brd.get("id", ""), **story} for story in stories]


async def generate_copilot_prompt(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
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

    prompt = build_prompt(system_prompt, user_prompt)
    return await call_genai(prompt)


async def find_related_stories(
    call_genai: CallGenAI,
    build_prompt: BuildPrompt,
    feature_description: str,
    jira_stories: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
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

    prompt = build_prompt(system_prompt, user_prompt)
    response_text = await call_genai(prompt)
    
    try:
        related = parse_json_response(response_text)
        return related if isinstance(related, list) else []
    except:
        return []
