"""RAGAS evaluation metrics API router."""
from fastapi import APIRouter, Request, Query
from typing import Optional
from repositories import storage
from api.v1.auth import get_current_user
from core.logging import log_info, log_error
from core.db.postgres import get_postgres_connection
from psycopg2.extras import RealDictCursor
from utils.exceptions import internal_error
from utils.response import success_response

router = APIRouter(tags=["ragas"])


@router.get("/ragas/evaluations")
async def get_evaluations(
    http_request: Request,
    project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        user = get_current_user(http_request)
        if not user:
            return success_response([])

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if project_id:
                cur.execute("""
                    SELECT * FROM rag_evaluations
                    WHERE project_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (project_id, limit, offset))
            else:
                cur.execute("""
                    SELECT * FROM rag_evaluations
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))

            rows = cur.fetchall()
            evaluations = []
            for row in rows:
                evaluations.append(_row_to_dict(row))
            return success_response(evaluations)
        finally:
            conn.close()

    except Exception as e:
        log_error("Error fetching RAGAS evaluations", "ragas", e)
        raise internal_error("Failed to fetch evaluations")


@router.get("/ragas/stats")
async def get_stats(
    http_request: Request,
    project_id: Optional[str] = Query(None),
):
    try:
        user = get_current_user(http_request)
        if not user:
            return success_response({})

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            where_clause = "WHERE project_id = %s" if project_id else ""
            params = (project_id,) if project_id else ()

            cur.execute(f"""
                SELECT
                    COUNT(*) as total_evaluations,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'running') as running,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    ROUND(AVG(faithfulness)::numeric, 3) as avg_faithfulness,
                    ROUND(AVG(answer_relevancy)::numeric, 3) as avg_answer_relevancy,
                    ROUND(AVG(context_relevancy)::numeric, 3) as avg_context_relevancy,
                    ROUND(AVG(context_precision)::numeric, 3) as avg_context_precision,
                    ROUND(AVG(hallucination_score)::numeric, 3) as avg_hallucination_score,
                    ROUND(AVG(overall_score)::numeric, 3) as avg_overall_score,
                    ROUND(AVG(context_chunks_count)::numeric, 1) as avg_chunks_count,
                    ROUND(AVG(avg_chunk_score)::numeric, 3) as avg_retrieval_score,
                    MIN(overall_score) as min_overall_score,
                    MAX(overall_score) as max_overall_score
                FROM rag_evaluations
                {where_clause}
            """, params)

            row = cur.fetchone()

            cur.execute(f"""
                SELECT
                    CASE
                        WHEN overall_score >= 0.8 THEN 'excellent'
                        WHEN overall_score >= 0.6 THEN 'good'
                        WHEN overall_score >= 0.4 THEN 'fair'
                        ELSE 'poor'
                    END as quality_tier,
                    COUNT(*) as count
                FROM rag_evaluations
                {where_clause}
                {"AND" if where_clause else "WHERE"} status = 'completed' AND overall_score IS NOT NULL
                GROUP BY quality_tier
                ORDER BY quality_tier
            """, params)

            tiers = {r["quality_tier"]: r["count"] for r in cur.fetchall()}

            cur.execute(f"""
                SELECT
                    DATE(created_at) as eval_date,
                    COUNT(*) as count,
                    ROUND(AVG(overall_score)::numeric, 3) as avg_score
                FROM rag_evaluations
                {where_clause}
                {"AND" if where_clause else "WHERE"} status = 'completed'
                GROUP BY DATE(created_at)
                ORDER BY eval_date DESC
                LIMIT 30
            """, params)

            trend = [
                {
                    "date": str(r["eval_date"]),
                    "count": r["count"],
                    "avgScore": float(r["avg_score"]) if r["avg_score"] else None,
                }
                for r in cur.fetchall()
            ]

            stats = {
                "totalEvaluations": row["total_evaluations"],
                "completed": row["completed"],
                "running": row["running"],
                "failed": row["failed"],
                "pending": row["pending"],
                "avgFaithfulness": float(row["avg_faithfulness"]) if row["avg_faithfulness"] else None,
                "avgAnswerRelevancy": float(row["avg_answer_relevancy"]) if row["avg_answer_relevancy"] else None,
                "avgContextRelevancy": float(row["avg_context_relevancy"]) if row["avg_context_relevancy"] else None,
                "avgContextPrecision": float(row["avg_context_precision"]) if row["avg_context_precision"] else None,
                "avgHallucinationScore": float(row["avg_hallucination_score"]) if row["avg_hallucination_score"] else None,
                "avgOverallScore": float(row["avg_overall_score"]) if row["avg_overall_score"] else None,
                "avgChunksCount": float(row["avg_chunks_count"]) if row["avg_chunks_count"] else None,
                "avgRetrievalScore": float(row["avg_retrieval_score"]) if row["avg_retrieval_score"] else None,
                "minOverallScore": float(row["min_overall_score"]) if row["min_overall_score"] else None,
                "maxOverallScore": float(row["max_overall_score"]) if row["max_overall_score"] else None,
                "qualityTiers": tiers,
                "trend": trend,
            }

            return success_response(stats)
        finally:
            conn.close()

    except Exception as e:
        log_error("Error fetching RAGAS stats", "ragas", e)
        raise internal_error("Failed to fetch evaluation stats")


@router.get("/ragas/evaluations/{evaluation_id}")
async def get_evaluation_detail(
    http_request: Request,
    evaluation_id: str,
):
    try:
        user = get_current_user(http_request)
        if not user:
            return success_response(None)

        result = storage.get_rag_evaluation(evaluation_id)
        return success_response(result)

    except Exception as e:
        log_error("Error fetching RAGAS evaluation detail", "ragas", e)
        raise internal_error("Failed to fetch evaluation detail")


@router.delete("/ragas/evaluations/{evaluation_id}")
async def delete_evaluation(
    http_request: Request,
    evaluation_id: str,
):
    try:
        user = get_current_user(http_request)
        if not user:
            raise internal_error("Authentication required")

        conn = get_postgres_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM rag_evaluations WHERE id = %s", (evaluation_id,))
            deleted = cur.rowcount
            conn.commit()
            if deleted == 0:
                raise internal_error("Evaluation not found")
            log_info(f"Deleted RAGAS evaluation {evaluation_id}", "ragas")
            return success_response({"deleted": True, "id": evaluation_id})
        finally:
            conn.close()

    except Exception as e:
        log_error(f"Error deleting RAGAS evaluation {evaluation_id}", "ragas", e)
        raise internal_error("Failed to delete evaluation")


def _row_to_dict(row) -> dict:
    if not row:
        return {}
    import json
    details = row.get("evaluation_details", {})
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}

    return {
        "id": row["id"],
        "projectId": row["project_id"],
        "featureRequestId": row.get("feature_request_id"),
        "brdId": row.get("brd_id"),
        "featureTitle": row.get("feature_title", ""),
        "status": row["status"],
        "faithfulness": row.get("faithfulness"),
        "answerRelevancy": row.get("answer_relevancy"),
        "contextRelevancy": row.get("context_relevancy"),
        "contextPrecision": row.get("context_precision"),
        "hallucinationScore": row.get("hallucination_score"),
        "overallScore": row.get("overall_score"),
        "contextChunksCount": row.get("context_chunks_count", 0),
        "avgChunkScore": row.get("avg_chunk_score"),
        "modelUsed": row.get("model_used"),
        "evaluationDetails": details,
        "errorMessage": row.get("error_message"),
        "createdAt": row["created_at"].isoformat() if hasattr(row.get("created_at"), "isoformat") else str(row.get("created_at", "")),
        "completedAt": row["completed_at"].isoformat() if row.get("completed_at") and hasattr(row["completed_at"], "isoformat") else None,
    }
