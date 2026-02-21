"""RAGAS-style evaluation service for BRD generation RAG calls.

Implements LLM-as-judge evaluation of 5 RAGAS metrics:
- Faithfulness: Is the BRD factually consistent with retrieved context?
- Answer Relevancy: Is the BRD relevant to the feature request?
- Context Relevancy: Are the retrieved context sources relevant to the feature request?
- Context Precision: Are the most relevant chunks ranked highest?
- Hallucination: Does the BRD contain fabricated claims not grounded in context?

Context for evaluation combines three sources:
1. MongoDB Knowledge Base chunks (retrieved via vector/keyword search)
2. Code Documentation (generated technical docs from repo analysis)
3. Existing System Context (database schema, architecture, tech stack)
"""
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from core.logging import log_info, log_error, log_warning
from repositories.storage import storage


FAITHFULNESS_PROMPT = """You are an expert evaluator assessing FAITHFULNESS — whether the generated BRD is grounded in and aligned with the retrieved context.

TASK: Evaluate whether the claims, technical details, and statements in the GENERATED BRD are factually supported by and aligned with the RETRIEVED CONTEXT.
A faithful BRD only makes project-specific claims that can be directly traced back to the provided context documents. General software engineering best practices are acceptable without context support.

The RETRIEVED CONTEXT below combines three sources:
1. Knowledge Base documents (uploaded project-specific docs)
2. Code Documentation (auto-generated technical docs from repo analysis)
3. Existing System Context (database schema, architecture, tech stack)

FEATURE REQUEST:
{question}

RETRIEVED CONTEXT (Combined: KB Documents + Code Documentation + System Context):
{context}

GENERATED BRD OUTPUT (excerpt):
{answer}

EVALUATION INSTRUCTIONS:
1. Identify all project-specific factual claims in the BRD (system names, integrations, business rules, constraints, technology choices, API details)
2. For each project-specific claim, verify it is explicitly stated or directly inferable from the retrieved context
3. General best-practice statements (e.g., "use HTTPS", "follow SOLID principles") are acceptable without context backing
4. If the BRD introduces project-specific details not found in the context, it is NOT faithful — flag it as unsupported
5. Pay special attention to: system architecture claims, existing feature descriptions, data model assertions, and integration details

Score from 0.0 to 1.0 where:
- 1.0 = All project-specific claims are directly traceable to the context
- 0.7 = Most claims are supported, minor details lack context backing
- 0.5 = Mix of supported and unsupported project-specific claims
- 0.3 = Many project-specific claims cannot be traced to context
- 0.0 = BRD makes project-specific claims entirely unrelated to context

Respond ONLY with valid JSON:
{{"score": <float>, "reasoning": "<brief explanation>"}}"""

ANSWER_RELEVANCY_PROMPT = """You are an expert evaluator assessing ANSWER RELEVANCY.

TASK: Evaluate whether the GENERATED BRD directly addresses and is relevant to the FEATURE REQUEST.
A relevant BRD focuses on the requested feature and provides useful, actionable requirements.

FEATURE REQUEST:
{question}

GENERATED BRD OUTPUT (excerpt):
{answer}

EVALUATION INSTRUCTIONS:
1. Does the BRD address the specific feature/bug/enhancement requested?
2. Are the requirements, scope, and objectives aligned with the request?
3. Is the content actionable and specific rather than generic filler?
4. Does it cover the key aspects the feature request implies?

Score from 0.0 to 1.0 where:
- 1.0 = BRD directly and comprehensively addresses the feature request
- 0.5 = BRD partially addresses the request or includes significant off-topic content
- 0.0 = BRD is irrelevant to the feature request

Respond ONLY with valid JSON:
{{"score": <float>, "reasoning": "<brief explanation>"}}"""

CONTEXT_RELEVANCY_PROMPT = """You are an expert evaluator assessing CONTEXT RELEVANCY.

TASK: Evaluate whether the RETRIEVED CONTEXT is relevant to the FEATURE REQUEST.
Relevant context provides useful information for generating requirements about the requested feature.

The RETRIEVED CONTEXT below combines three sources:
1. Knowledge Base documents (uploaded project-specific docs)
2. Code Documentation (auto-generated technical docs from repo analysis)
3. Existing System Context (database schema, architecture, tech stack)

FEATURE REQUEST:
{question}

RETRIEVED CONTEXT (Combined: KB Documents + Code Documentation + System Context):
{context}

EVALUATION INSTRUCTIONS:
1. For each context section/chunk, assess if it contains information useful for the feature request
2. Consider whether the context provides: technical details, business rules, constraints, related functionality, domain knowledge, architecture info, or data model details
3. Irrelevant context wastes LLM capacity and may cause hallucinations
4. Evaluate each source type separately — KB docs, code documentation, and system context may each contribute differently

Score from 0.0 to 1.0 where:
- 1.0 = All retrieved context is highly relevant to the feature request
- 0.5 = Some context is relevant, some is not
- 0.0 = Retrieved context is mostly irrelevant

Respond ONLY with valid JSON:
{{"score": <float>, "reasoning": "<brief explanation>"}}"""

CONTEXT_PRECISION_PROMPT = """You are an expert evaluator assessing CONTEXT PRECISION (ranking quality).

TASK: Evaluate whether the most relevant context sources are ranked and ordered effectively.
Good precision means the retrieval system puts the best information first and the most useful sources are prioritized.

Note: Context includes KB chunks (with relevance scores), code documentation, and system context.
KB chunks are ranked by retrieval score; documentation and system context are included as supplementary sources.

FEATURE REQUEST:
{question}

RETRIEVED CONTEXT SOURCES (ordered by retrieval rank, with scores where applicable):
{ranked_context}

EVALUATION INSTRUCTIONS:
1. Review the chunks in order from first to last
2. Are the most informative/relevant chunks ranked first?
3. Would reordering the chunks improve the quality of context provided to the LLM?
4. Consider if the relevance scores correlate with actual usefulness

Score from 0.0 to 1.0 where:
- 1.0 = Chunks are perfectly ordered by relevance (best first)
- 0.5 = Ordering is somewhat correct but could be improved
- 0.0 = Chunks are ordered poorly (least relevant first)

Respond ONLY with valid JSON:
{{"score": <float>, "reasoning": "<brief explanation>"}}"""

HALLUCINATION_PROMPT = """You are an expert evaluator detecting HALLUCINATIONS in a generated document.

TASK: Identify whether the GENERATED BRD contains fabricated, invented, or hallucinated information — claims that are NOT present in the RETRIEVED CONTEXT and are NOT general software engineering knowledge.

Hallucinations include:
- Invented system names, API endpoints, database tables, or services that don't exist in the context
- Fabricated business rules, constraints, or requirements not mentioned in context
- Made-up integration details, third-party service references, or technical specifications
- False claims about existing system behavior, architecture, or data flows
- Invented user roles, workflows, or process steps not supported by context

The RETRIEVED CONTEXT below combines three sources:
1. Knowledge Base documents (uploaded project-specific docs)
2. Code Documentation (auto-generated technical docs from repo analysis)
3. Existing System Context (database schema, architecture, tech stack)

FEATURE REQUEST:
{question}

RETRIEVED CONTEXT (Combined: KB Documents + Code Documentation + System Context):
{context}

GENERATED BRD OUTPUT (excerpt):
{answer}

EVALUATION INSTRUCTIONS:
1. Carefully read the generated BRD and identify all specific, project-level claims
2. For each claim, check: Is it present in the context? Is it a reasonable general practice? Or is it fabricated?
3. List the hallucinated claims you find (if any)
4. A HIGHER score means FEWER hallucinations (the BRD is more trustworthy)
5. Even one significant hallucination (e.g., inventing a non-existent API or system component) should notably reduce the score

Score from 0.0 to 1.0 where:
- 1.0 = No hallucinations detected; all project-specific claims are grounded in context or are clearly general practices
- 0.8 = Minor hallucinations only (e.g., slightly embellished details that don't change meaning)
- 0.5 = Several hallucinated claims mixed with grounded ones
- 0.3 = Significant hallucinations — invented systems, APIs, or business rules
- 0.0 = Heavily hallucinated — most project-specific content is fabricated

Respond ONLY with valid JSON:
{{"score": <float>, "reasoning": "<list the specific hallucinations found, or state none were found>"}}"""


def _parse_score_response(response_text: str) -> Dict[str, Any]:
    try:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        score = float(result.get("score", 0))
        score = max(0.0, min(1.0, score))
        return {
            "score": round(score, 3),
            "reasoning": result.get("reasoning", ""),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        log_warning(f"Failed to parse RAGAS score response: {e}", "ragas")
        return {"score": 0.0, "reasoning": f"Parse error: {str(e)}"}


async def _evaluate_metric(
    call_genai,
    prompt_template: str,
    variables: Dict[str, str],
    metric_name: str,
) -> Dict[str, Any]:
    try:
        prompt = prompt_template.format(**variables)
        response = await call_genai(prompt)
        result = _parse_score_response(response)
        log_info(f"RAGAS {metric_name}: {result['score']:.3f}", "ragas")
        return result
    except Exception as e:
        log_error(f"RAGAS {metric_name} evaluation failed: {e}", "ragas")
        return {"score": 0.0, "reasoning": f"Evaluation error: {str(e)}"}


def _build_question(feature_request: Dict[str, Any]) -> str:
    title = feature_request.get("title", "")
    description = feature_request.get("description", "")
    request_type = feature_request.get("requestType", "feature")
    return f"[{request_type.upper()}] {title}\n{description}"


def _build_kb_context(knowledge_sources: List[Dict[str, Any]]) -> str:
    if not knowledge_sources:
        return ""
    parts = []
    for i, src in enumerate(knowledge_sources, 1):
        preview = src.get("chunkPreview", src.get("content", ""))[:500]
        filename = src.get("filename", "Unknown")
        score = src.get("relevanceScore", src.get("score", 0))
        parts.append(f"--- KB Chunk {i} (source: {filename}, score: {score:.3f}) ---\n{preview}")
    return "\n\n".join(parts)


def _build_documentation_context(documentation: Optional[Dict[str, Any]]) -> str:
    if not documentation:
        return ""
    parts = []
    title = documentation.get("title", "")
    if title:
        parts.append(f"Project: {title}")

    summary = documentation.get("content", "")
    if summary:
        parts.append(f"Summary: {summary[:1000]}")

    sections = documentation.get("sections", [])
    if sections and isinstance(sections, list):
        for section in sections[:10]:
            if isinstance(section, dict):
                sec_title = section.get("title", "Untitled")
                sec_content = section.get("content", "")
                if sec_content:
                    parts.append(f"--- {sec_title} ---\n{sec_content[:500]}")
            elif isinstance(section, str):
                parts.append(section[:500])

    return "\n\n".join(parts)


def _build_system_context(
    analysis: Optional[Dict[str, Any]],
    database_schema: Optional[Dict[str, Any]],
) -> str:
    parts = []

    if database_schema:
        table_descriptions = []
        for table in database_schema.get("tables", [])[:20]:
            columns = []
            for col in table.get("columns", [])[:15]:
                desc = f"    - {col['name']}: {col['dataType']}"
                if col.get("isPrimaryKey"):
                    desc += " (PK)"
                if col.get("isForeignKey"):
                    desc += f" (FK -> {col.get('references', '?')})"
                columns.append(desc)
            table_descriptions.append(f"  {table['name']}:\n" + "\n".join(columns))
        parts.append("Database Schema:\n" + "\n".join(table_descriptions))

    if analysis:
        arch = analysis.get("architecture", "")
        if arch:
            parts.append(f"Architecture: {arch[:500]}")
        tech_stack = analysis.get("techStack", {})
        if tech_stack:
            parts.append(f"Tech Stack: {json.dumps(tech_stack)[:500]}")
        features = analysis.get("features", [])
        if features:
            feature_names = ", ".join(f.get("name", "") for f in features[:20])
            parts.append(f"Features: {feature_names}")

    return "\n\n".join(parts)


def _build_context_text(
    knowledge_sources: List[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]] = None,
    analysis: Optional[Dict[str, Any]] = None,
    database_schema: Optional[Dict[str, Any]] = None,
) -> str:
    sections = []

    kb_text = _build_kb_context(knowledge_sources)
    if kb_text:
        sections.append(f"=== KNOWLEDGE BASE DOCUMENTS ===\n{kb_text}\n=== END KNOWLEDGE BASE ===")

    doc_text = _build_documentation_context(documentation)
    if doc_text:
        sections.append(f"=== CODE DOCUMENTATION ===\n{doc_text}\n=== END CODE DOCUMENTATION ===")

    sys_text = _build_system_context(analysis, database_schema)
    if sys_text:
        sections.append(f"=== EXISTING SYSTEM CONTEXT ===\n{sys_text}\n=== END EXISTING SYSTEM CONTEXT ===")

    if not sections:
        return "(No context retrieved)"

    return "\n\n".join(sections)


def _build_ranked_context(
    knowledge_sources: List[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]] = None,
    analysis: Optional[Dict[str, Any]] = None,
    database_schema: Optional[Dict[str, Any]] = None,
) -> str:
    parts = []

    for i, src in enumerate(knowledge_sources, 1):
        preview = src.get("chunkPreview", src.get("content", ""))[:500]
        filename = src.get("filename", "Unknown")
        score = src.get("relevanceScore", src.get("score", 0))
        parts.append(f"Rank {i} | Score: {score:.4f} | Source: {filename} [KB]\n{preview}")

    rank_offset = len(knowledge_sources)

    doc_text = _build_documentation_context(documentation)
    if doc_text:
        rank_offset += 1
        parts.append(f"Rank {rank_offset} | Source: Code Documentation [DOC]\n{doc_text[:800]}")

    sys_text = _build_system_context(analysis, database_schema)
    if sys_text:
        rank_offset += 1
        parts.append(f"Rank {rank_offset} | Source: System Context [SYS]\n{sys_text[:800]}")

    if not parts:
        return "(No context retrieved)"

    return "\n\n".join(parts)


def _build_answer_text(brd_content: Dict[str, Any]) -> str:
    parts = []
    for section_key in [
        "overview", "objectives", "scope", "existingSystemContext",
        "functionalRequirements", "nonFunctionalRequirements",
        "technicalConsiderations", "integrationRequirements",
    ]:
        section = brd_content.get(section_key)
        if section:
            if isinstance(section, dict):
                parts.append(json.dumps(section, indent=1)[:600])
            elif isinstance(section, str):
                parts.append(section[:600])
    combined = "\n\n".join(parts)
    return combined[:4000]


async def run_ragas_evaluation(
    feature_request: Dict[str, Any],
    knowledge_sources: List[Dict[str, Any]],
    brd_content: Dict[str, Any],
    project_id: str,
    feature_request_id: Optional[str] = None,
    brd_id: Optional[str] = None,
    documentation: Optional[Dict[str, Any]] = None,
    database_schema: Optional[Dict[str, Any]] = None,
    analysis: Optional[Dict[str, Any]] = None,
) -> str:
    from utils.pwc_llm import call_pwc_genai_async

    eval_id = None
    try:
        eval_record = storage.create_rag_evaluation({
            "projectId": project_id,
            "featureRequestId": feature_request_id,
            "brdId": brd_id,
            "featureTitle": feature_request.get("title", "")[:200],
            "status": "running",
            "contextChunksCount": len(knowledge_sources),
            "avgChunkScore": round(
                sum(s.get("relevanceScore", s.get("score", 0)) for s in knowledge_sources) / max(len(knowledge_sources), 1),
                4,
            ) if knowledge_sources else None,
        })
        eval_id = eval_record["id"]
        log_info(
            f"RAGAS evaluation started: {eval_id} — "
            f"KB chunks: {len(knowledge_sources)}, "
            f"has_docs: {bool(documentation)}, "
            f"has_db_schema: {bool(database_schema)}, "
            f"has_analysis: {bool(analysis)}",
            "ragas",
        )

        async def call_genai(prompt: str) -> str:
            return await call_pwc_genai_async(
                prompt=prompt,
                task_name="ragas_evaluation",
            )

        question = _build_question(feature_request)
        context = _build_context_text(knowledge_sources, documentation, analysis, database_schema)
        ranked_context = _build_ranked_context(knowledge_sources, documentation, analysis, database_schema)
        answer = _build_answer_text(brd_content)

        has_context = bool(knowledge_sources) or bool(documentation) or bool(database_schema) or bool(analysis)

        if has_context:
            faithfulness_task = _evaluate_metric(
                call_genai, FAITHFULNESS_PROMPT,
                {"question": question, "context": context, "answer": answer},
                "faithfulness",
            )
            context_relevancy_task = _evaluate_metric(
                call_genai, CONTEXT_RELEVANCY_PROMPT,
                {"question": question, "context": context},
                "context_relevancy",
            )
            context_precision_task = _evaluate_metric(
                call_genai, CONTEXT_PRECISION_PROMPT,
                {"question": question, "ranked_context": ranked_context},
                "context_precision",
            )
            hallucination_task = _evaluate_metric(
                call_genai, HALLUCINATION_PROMPT,
                {"question": question, "context": context, "answer": answer},
                "hallucination",
            )
        else:
            async def _null_result():
                return {"score": None, "reasoning": "No context chunks retrieved"}
            faithfulness_task = _null_result()
            context_relevancy_task = _null_result()
            context_precision_task = _null_result()
            hallucination_task = _null_result()

        answer_relevancy_task = _evaluate_metric(
            call_genai, ANSWER_RELEVANCY_PROMPT,
            {"question": question, "answer": answer},
            "answer_relevancy",
        )

        results = await asyncio.gather(
            faithfulness_task,
            answer_relevancy_task,
            context_relevancy_task,
            context_precision_task,
            hallucination_task,
            return_exceptions=True,
        )

        metrics: Dict[str, Any] = {}
        metric_names = ["faithfulness", "answer_relevancy", "context_relevancy", "context_precision", "hallucination"]
        details: Dict[str, Any] = {}
        for name, result in zip(metric_names, results):
            if isinstance(result, BaseException):
                log_error(f"RAGAS {name} failed: {result}", "ragas")
                metrics[name] = None
                details[name] = {"error": str(result)}
            elif isinstance(result, dict):
                metrics[name] = result.get("score")
                details[name] = result
            else:
                metrics[name] = None
                details[name] = {"error": "Unexpected result type"}

        valid_scores = [v for v in metrics.values() if v is not None]
        overall = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else None

        update_data = {
            "status": "completed",
            "faithfulness": metrics.get("faithfulness"),
            "answerRelevancy": metrics.get("answer_relevancy"),
            "contextRelevancy": metrics.get("context_relevancy"),
            "contextPrecision": metrics.get("context_precision"),
            "hallucinationScore": metrics.get("hallucination"),
            "overallScore": overall,
            "evaluationDetails": details,
            "completedAt": datetime.utcnow().isoformat(),
        }
        storage.update_rag_evaluation(eval_id, update_data)

        log_info(
            f"RAGAS evaluation completed: {eval_id} — "
            f"F:{metrics.get('faithfulness')}, AR:{metrics.get('answer_relevancy')}, "
            f"CR:{metrics.get('context_relevancy')}, CP:{metrics.get('context_precision')}, "
            f"H:{metrics.get('hallucination')}, Overall:{overall}",
            "ragas",
        )
        return eval_id

    except Exception as e:
        log_error(f"RAGAS evaluation failed: {e}", "ragas")
        if eval_id:
            try:
                storage.update_rag_evaluation(eval_id, {
                    "status": "failed",
                    "errorMessage": str(e)[:500],
                })
            except Exception:
                pass
        return eval_id or ""
