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


def _clamp_score(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return max(0.0, min(1.0, round(f, 3)))
    except (TypeError, ValueError):
        return None


async def _eval_faithfulness(llm, user_input: str, response: str, retrieved_contexts: List[str]) -> Dict[str, Any]:
    try:
        from ragas.metrics.collections import Faithfulness
        metric = Faithfulness(llm=llm)

        statements = await metric._create_statements(user_input, response)
        if not statements:
            return {"score": None, "reasoning": "No atomic statements could be extracted from the response."}

        context_str = "\n".join(retrieved_contexts)
        verdicts = await metric._create_verdicts(statements, context_str)
        score = _clamp_score(metric._compute_score(verdicts))

        statement_details = []
        for stmt in verdicts.statements:
            statement_details.append({
                "statement": stmt.statement[:300],
                "verdict": "faithful" if stmt.verdict == 1 else "not faithful",
                "reason": stmt.reason,
            })

        faithful_count = sum(1 for s in verdicts.statements if s.verdict == 1)
        total = len(verdicts.statements)
        summary = f"{faithful_count}/{total} statements are faithful to the retrieved context."

        if statement_details:
            unfaithful = [s for s in statement_details if s["verdict"] == "not faithful"]
            if unfaithful:
                summary += f" {len(unfaithful)} statement(s) not grounded in context: "
                summary += "; ".join(f'"{s["statement"][:100]}..." — {s["reason"]}' for s in unfaithful[:5])

        log_info(f"RAGAS faithfulness: {score} ({faithful_count}/{total} faithful)", "ragas")
        return {"score": score, "reasoning": summary, "details": statement_details}
    except Exception as e:
        log_error(f"RAGAS faithfulness evaluation failed: {e}", "ragas")
        return {"score": None, "reasoning": f"Evaluation error: {str(e)}"}


async def _eval_answer_relevancy(llm, embeddings, user_input: str, response: str) -> Dict[str, Any]:
    try:
        from ragas.metrics.collections import AnswerRelevancy
        from ragas.metrics.collections.answer_relevancy.util import AnswerRelevanceInput, AnswerRelevanceOutput
        import numpy as np

        metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
        generated_questions = []
        noncommittal_flags = []

        for _ in range(metric.strictness):
            input_data = AnswerRelevanceInput(response=response)
            prompt_string = metric.prompt.to_string(input_data)
            result = await metric.llm.agenerate(prompt_string, AnswerRelevanceOutput)
            if result.question:
                generated_questions.append(result.question)
                noncommittal_flags.append(result.noncommittal)

        if not generated_questions:
            return {"score": 0.0, "reasoning": "No questions could be generated from the response — likely evasive or empty."}

        all_noncommittal = np.all(noncommittal_flags)

        question_vec = np.asarray(await metric.embeddings.aembed_text(user_input)).reshape(1, -1)
        gen_question_vec = np.asarray(await metric.embeddings.aembed_texts(generated_questions)).reshape(len(generated_questions), -1)
        norm = np.linalg.norm(gen_question_vec, axis=1) * np.linalg.norm(question_vec, axis=1)
        norm = np.where(norm == 0, 1e-10, norm)
        cosine_sim = np.dot(gen_question_vec, question_vec.T).reshape(-1) / norm
        cosine_sim = np.nan_to_num(cosine_sim, nan=0.0)
        raw_score = cosine_sim.mean() * int(not all_noncommittal)
        score = _clamp_score(raw_score)

        question_details = []
        for i, q in enumerate(generated_questions):
            question_details.append({
                "generated_question": q,
                "similarity": round(float(cosine_sim[i]), 3),
                "noncommittal": bool(noncommittal_flags[i]),
            })

        avg_sim = round(float(cosine_sim.mean()), 3)
        summary = f"Generated {len(generated_questions)} questions from the response. Average cosine similarity to original question: {avg_sim}."
        if all_noncommittal:
            summary += " Response was classified as noncommittal/evasive, score reduced to 0."

        log_info(f"RAGAS answer_relevancy: {score} (avg_sim={avg_sim})", "ragas")
        return {"score": score, "reasoning": summary, "details": question_details}
    except Exception as e:
        log_error(f"RAGAS answer_relevancy evaluation failed: {e}", "ragas")
        return {"score": None, "reasoning": f"Evaluation error: {str(e)}"}


async def _eval_context_precision(llm, user_input: str, response: str, retrieved_contexts: List[str]) -> Dict[str, Any]:
    try:
        from ragas.metrics.collections import ContextPrecisionWithoutReference
        from ragas.metrics.collections.context_precision.util import ContextPrecisionInput, ContextPrecisionOutput
        metric = ContextPrecisionWithoutReference(llm=llm)

        verdicts = []
        for context in retrieved_contexts:
            input_data = ContextPrecisionInput(question=user_input, context=context, answer=response)
            prompt_string = metric.prompt.to_string(input_data)
            result = await metric.llm.agenerate(prompt_string, ContextPrecisionOutput)
            verdicts.append(result.verdict)

        score = _clamp_score(metric._calculate_average_precision(verdicts))

        chunk_details = []
        for i, v in enumerate(verdicts):
            chunk_details.append({
                "chunk_index": i + 1,
                "relevant": bool(v),
                "context_preview": retrieved_contexts[i][:150] + "..." if len(retrieved_contexts[i]) > 150 else retrieved_contexts[i],
            })

        relevant_count = sum(1 for v in verdicts if v)
        summary = f"{relevant_count}/{len(verdicts)} retrieved chunks were judged relevant to answering the question. Average precision score: {score}."

        log_info(f"RAGAS context_precision: {score} ({relevant_count}/{len(verdicts)} relevant)", "ragas")
        return {"score": score, "reasoning": summary, "details": chunk_details}
    except Exception as e:
        log_error(f"RAGAS context_precision evaluation failed: {e}", "ragas")
        return {"score": None, "reasoning": f"Evaluation error: {str(e)}"}


async def _eval_context_relevance(llm, user_input: str, retrieved_contexts: List[str]) -> Dict[str, Any]:
    try:
        from ragas.metrics.collections import ContextRelevance
        metric = ContextRelevance(llm=llm)
        result = await metric.ascore(user_input=user_input, retrieved_contexts=retrieved_contexts)
        score = _clamp_score(result)

        summary = f"Context relevance evaluated using dual-judge scoring. Score: {score}. " \
                  f"Measures how relevant the {len(retrieved_contexts)} retrieved context chunks are to the original question."
        log_info(f"RAGAS context_relevance: {score}", "ragas")
        return {"score": score, "reasoning": summary}
    except Exception as e:
        log_error(f"RAGAS context_relevance evaluation failed: {e}", "ragas")
        return {"score": None, "reasoning": f"Evaluation error: {str(e)}"}


async def _eval_groundedness(llm, response: str, retrieved_contexts: List[str]) -> Dict[str, Any]:
    try:
        from ragas.metrics.collections import ResponseGroundedness
        metric = ResponseGroundedness(llm=llm)
        result = await metric.ascore(response=response, retrieved_contexts=retrieved_contexts)
        score = _clamp_score(result)

        summary = f"Response groundedness evaluated using dual-judge scoring. Score: {score}. " \
                  f"Measures how well the response is grounded in the {len(retrieved_contexts)} retrieved context chunks."
        log_info(f"RAGAS groundedness: {score}", "ragas")
        return {"score": score, "reasoning": summary}
    except Exception as e:
        log_error(f"RAGAS groundedness evaluation failed: {e}", "ragas")
        return {"score": None, "reasoning": f"Evaluation error: {str(e)}"}


async def _evaluate_with_ragas(
    user_input: str,
    response: str,
    retrieved_contexts: List[str],
) -> Dict[str, Any]:
    from evaluation.pwc_ragas_llm import PwcGenAIRagasLLM, PwcGenAIRagasEmbedding

    llm = PwcGenAIRagasLLM(task_name="ragas_evaluation")
    embeddings = PwcGenAIRagasEmbedding(task_name="ragas_embedding")

    (
        faithfulness_result,
        answer_relevancy_result,
        context_precision_result,
        context_relevance_result,
        groundedness_result,
    ) = await asyncio.gather(
        _eval_faithfulness(llm, user_input, response, retrieved_contexts),
        _eval_answer_relevancy(llm, embeddings, user_input, response),
        _eval_context_precision(llm, user_input, response, retrieved_contexts),
        _eval_context_relevance(llm, user_input, retrieved_contexts),
        _eval_groundedness(llm, response, retrieved_contexts),
        return_exceptions=False,
    )

    faithfulness_score = faithfulness_result["score"]
    groundedness_score = groundedness_result["score"]
    hallucination_score = round(1.0 - faithfulness_score, 3) if faithfulness_score is not None else None

    unfaithful_details = []
    if faithfulness_result.get("details"):
        unfaithful_details = [d for d in faithfulness_result["details"] if d["verdict"] == "not faithful"]

    hallucination_reasoning = f"Derived from faithfulness (1 - {faithfulness_score}). "
    hallucination_reasoning += f"Groundedness: {groundedness_score}. "
    if unfaithful_details:
        hallucination_reasoning += f"{len(unfaithful_details)} unfaithful statement(s) detected: "
        hallucination_reasoning += "; ".join(
            f'"{d["statement"][:100]}" — {d["reason"]}' for d in unfaithful_details[:5]
        )
    else:
        hallucination_reasoning += "No fabricated claims detected in the response."

    return {
        "faithfulness": faithfulness_result,
        "answer_relevancy": answer_relevancy_result,
        "context_relevancy": context_relevance_result,
        "context_precision": context_precision_result,
        "hallucination": {
            "score": hallucination_score,
            "reasoning": hallucination_reasoning,
            "details": unfaithful_details if unfaithful_details else None,
        },
    }


async def _evaluate_answer_relevancy_only(user_input: str, response: str) -> Dict[str, Any]:
    from evaluation.pwc_ragas_llm import PwcGenAIRagasLLM, PwcGenAIRagasEmbedding

    llm = PwcGenAIRagasLLM(task_name="ragas_evaluation")
    embeddings = PwcGenAIRagasEmbedding(task_name="ragas_embedding")
    return await _eval_answer_relevancy(llm, embeddings, user_input, response)


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
            results["answer_relevancy"] = await _evaluate_answer_relevancy_only(question, answer)

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
