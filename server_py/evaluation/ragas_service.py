"""RAGAS evaluation service for BRD generation RAG calls.

Uses the official ragas library (v0.4+) with a custom PwC GenAI LLM wrapper
to evaluate 5 metrics:
- Faithfulness: Is the BRD factually consistent with retrieved context?
- Answer Relevancy: Is the BRD relevant to the feature request?
- Context Relevancy: Are the retrieved context sources relevant?
- Context Precision: Are the most relevant chunks ranked highest?
- Hallucination: Does the BRD contain fabricated claims? (via Faithfulness inverse)

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
                col_name = col.get("name", "unknown")
                col_type = col.get("dataType", "unknown")
                desc = f"    - {col_name}: {col_type}"
                if col.get("isPrimaryKey"):
                    desc += " (PK)"
                if col.get("isForeignKey"):
                    desc += f" (FK -> {col.get('references', '?')})"
                columns.append(desc)
            table_name = table.get("name", "unknown_table")
            table_descriptions.append(f"  {table_name}:\n" + "\n".join(columns))
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


def _build_retrieved_contexts(
    knowledge_sources: List[Dict[str, Any]],
    documentation: Optional[Dict[str, Any]] = None,
    analysis: Optional[Dict[str, Any]] = None,
    database_schema: Optional[Dict[str, Any]] = None,
) -> List[str]:
    contexts = []
    for src in knowledge_sources:
        preview = src.get("chunkPreview", src.get("content", ""))[:500]
        filename = src.get("filename", "Unknown")
        score = src.get("relevanceScore", src.get("score", 0))
        contexts.append(f"[KB: {filename}, score: {score:.3f}] {preview}")
    doc_text = _build_documentation_context(documentation)
    if doc_text:
        contexts.append(f"[Code Documentation] {doc_text[:800]}")
    sys_text = _build_system_context(analysis, database_schema)
    if sys_text:
        contexts.append(f"[System Context] {sys_text[:800]}")
    return contexts


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


async def _evaluate_with_ragas(
    user_input: str,
    response: str,
    retrieved_contexts: List[str],
) -> Dict[str, Any]:
    from ragas import SingleTurnSample
    from ragas.metrics.collections import (
        Faithfulness,
        ContextPrecisionWithoutReference,
        AnswerRelevancy,
        ContextRelevance,
        ResponseGroundedness,
    )
    from evaluation.pwc_ragas_llm import PwcGenAIRagasLLM, PwcGenAIRagasEmbedding

    llm = PwcGenAIRagasLLM(task_name="ragas_evaluation")
    embeddings = PwcGenAIRagasEmbedding(task_name="ragas_embedding")

    sample = SingleTurnSample(
        user_input=user_input,
        response=response,
        retrieved_contexts=retrieved_contexts,
    )

    faithfulness_metric = Faithfulness(llm=llm)
    answer_relevancy_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
    context_precision_metric = ContextPrecisionWithoutReference(llm=llm)
    context_relevance_metric = ContextRelevance(llm=llm)
    groundedness_metric = ResponseGroundedness(llm=llm)

    async def _safe_score(metric, metric_name: str, sample: SingleTurnSample):
        try:
            score = await metric.single_turn_ascore(sample)
            score_val = float(score) if score is not None else None
            if score_val is not None:
                score_val = max(0.0, min(1.0, round(score_val, 3)))
            log_info(f"RAGAS {metric_name}: {score_val}", "ragas")
            return {"score": score_val, "reasoning": f"Evaluated by ragas {metric_name} metric"}
        except Exception as e:
            log_error(f"RAGAS {metric_name} evaluation failed: {e}", "ragas")
            return {"score": None, "reasoning": f"Evaluation error: {str(e)}"}

    faithfulness_result, answer_relevancy_result, context_precision_result, context_relevance_result, groundedness_result = await asyncio.gather(
        _safe_score(faithfulness_metric, "faithfulness", sample),
        _safe_score(answer_relevancy_metric, "answer_relevancy", sample),
        _safe_score(context_precision_metric, "context_precision", sample),
        _safe_score(context_relevance_metric, "context_relevance", sample),
        _safe_score(groundedness_metric, "response_groundedness", sample),
        return_exceptions=False,
    )

    faithfulness_score = faithfulness_result["score"]
    hallucination_score = round(1.0 - faithfulness_score, 3) if faithfulness_score is not None else None

    return {
        "faithfulness": faithfulness_result,
        "answer_relevancy": answer_relevancy_result,
        "context_relevancy": context_relevance_result,
        "context_precision": context_precision_result,
        "hallucination": {
            "score": hallucination_score,
            "reasoning": f"Derived from faithfulness (1 - {faithfulness_score}). "
                         f"Groundedness check: {groundedness_result['score']}. "
                         f"{groundedness_result['reasoning']}",
        },
    }


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
            f"RAGAS evaluation started (ragas library): {eval_id} — "
            f"KB chunks: {len(knowledge_sources)}, "
            f"has_docs: {bool(documentation)}, "
            f"has_db_schema: {bool(database_schema)}, "
            f"has_analysis: {bool(analysis)}",
            "ragas",
        )

        question = _build_question(feature_request)
        answer = _build_answer_text(brd_content)
        retrieved_contexts = _build_retrieved_contexts(
            knowledge_sources, documentation, analysis, database_schema
        )

        has_context = bool(retrieved_contexts)

        if has_context:
            results = await _evaluate_with_ragas(
                user_input=question,
                response=answer,
                retrieved_contexts=retrieved_contexts,
            )
        else:
            null_result = {"score": None, "reasoning": "No context retrieved — metric requires context"}
            results = {
                "faithfulness": null_result,
                "context_relevancy": null_result,
                "context_precision": null_result,
                "hallucination": null_result,
            }
            try:
                from ragas import SingleTurnSample
                from ragas.metrics.collections import AnswerRelevancy
                from evaluation.pwc_ragas_llm import PwcGenAIRagasLLM, PwcGenAIRagasEmbedding

                llm = PwcGenAIRagasLLM(task_name="ragas_evaluation")
                embeddings = PwcGenAIRagasEmbedding(task_name="ragas_embedding")
                ar_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
                sample = SingleTurnSample(
                    user_input=question,
                    response=answer,
                    retrieved_contexts=[],
                )
                score = await ar_metric.single_turn_ascore(sample)
                score_val = float(score) if score is not None else None
                if score_val is not None:
                    score_val = max(0.0, min(1.0, round(score_val, 3)))
                results["answer_relevancy"] = {
                    "score": score_val,
                    "reasoning": "Evaluated by ragas answer_relevancy metric (no context available)",
                }
                log_info(f"RAGAS answer_relevancy (no context): {score_val}", "ragas")
            except Exception as e:
                log_error(f"RAGAS answer_relevancy (no context) failed: {e}", "ragas")
                results["answer_relevancy"] = {
                    "score": None,
                    "reasoning": f"Evaluation error: {str(e)}",
                }

        metrics = {k: v["score"] for k, v in results.items()}
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
            "evaluationDetails": results,
            "completedAt": datetime.utcnow().isoformat(),
        }
        storage.update_rag_evaluation(eval_id, update_data)

        log_info(
            f"RAGAS evaluation completed (ragas library): {eval_id} — "
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
