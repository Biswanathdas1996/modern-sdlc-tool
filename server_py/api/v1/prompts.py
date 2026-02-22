"""Prompt management API router."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Request, Query, Body
from typing import Optional
from api.v1.auth import get_current_user
from core.logging import log_info, log_error
from core.db.postgres import get_postgres_connection
from psycopg2.extras import RealDictCursor
from utils.response import success_response

router = APIRouter(tags=["prompts"])


def _format_prompt(row) -> dict:
    return {
        "id": row["id"],
        "promptKey": row["prompt_key"],
        "category": row["category"],
        "content": row["content"],
        "description": row.get("description"),
        "promptType": row["prompt_type"],
        "isActive": row["is_active"],
        "version": row["version"],
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


@router.get("/prompts")
async def list_prompts(
    http_request: Request,
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    try:
        user = get_current_user(http_request)
        if not user:
            return {"success": False, "error": "Unauthorized"}

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            conditions = []
            params = []

            if category:
                conditions.append("category = %s")
                params.append(category)
            if is_active is not None:
                conditions.append("is_active = %s")
                params.append(is_active)
            if search:
                conditions.append("(prompt_key ILIKE %s OR content ILIKE %s)")
                params.extend([f"%{search}%", f"%{search}%"])

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            cur.execute(f"SELECT COUNT(*) as total FROM prompts {where}", params)
            total = cur.fetchone()["total"]

            cur.execute(f"""
                SELECT * FROM prompts {where}
                ORDER BY category, prompt_key, version DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])

            prompts = [_format_prompt(row) for row in cur.fetchall()]

            cur.execute("SELECT DISTINCT category FROM prompts ORDER BY category")
            categories = [row["category"] for row in cur.fetchall()]

            return success_response({
                "prompts": prompts,
                "total": total,
                "categories": categories,
            })
        finally:
            cur.close()
            conn.close()

    except Exception as e:
        log_error(f"Failed to list prompts: {e}", "prompts_api")
        return {"success": False, "error": str(e)}


@router.get("/prompts/{prompt_id}")
async def get_prompt(http_request: Request, prompt_id: str):
    try:
        user = get_current_user(http_request)
        if not user:
            return {"success": False, "error": "Unauthorized"}

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM prompts WHERE id = %s", (prompt_id,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": "Prompt not found"}

            cur.execute("""
                SELECT * FROM prompts
                WHERE prompt_key = %s AND category = %s
                ORDER BY version DESC
            """, (row["prompt_key"], row["category"]))
            versions = [_format_prompt(r) for r in cur.fetchall()]

            result = _format_prompt(row)
            result["versions"] = versions
            return success_response(result)
        finally:
            cur.close()
            conn.close()

    except Exception as e:
        log_error(f"Failed to get prompt: {e}", "prompts_api")
        return {"success": False, "error": str(e)}


@router.put("/prompts/{prompt_id}")
async def update_prompt(http_request: Request, prompt_id: str, body: dict = Body(...)):
    try:
        user = get_current_user(http_request)
        if not user or user.get("role") != "admin":
            return {"success": False, "error": "Admin access required"}

        content = body.get("content")
        description = body.get("description")
        is_active = body.get("isActive")

        if content is None and description is None and is_active is None:
            return {"success": False, "error": "No fields to update"}

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("SELECT * FROM prompts WHERE id = %s", (prompt_id,))
            existing = cur.fetchone()
            if not existing:
                return {"success": False, "error": "Prompt not found"}

            if content is not None and content != existing["content"]:
                cur.execute("UPDATE prompts SET is_active = false WHERE id = %s", (prompt_id,))

                new_id = str(uuid.uuid4())
                new_version = existing["version"] + 1
                cur.execute("""
                    INSERT INTO prompts (id, prompt_key, category, content, description, prompt_type, is_active, version, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, true, %s, NOW(), NOW())
                """, (
                    new_id, existing["prompt_key"], existing["category"],
                    content, description or existing.get("description"),
                    existing["prompt_type"], new_version,
                ))
                conn.commit()

                cur.execute("SELECT * FROM prompts WHERE id = %s", (new_id,))
                updated = cur.fetchone()

                from prompts import prompt_loader
                prompt_loader.invalidate_cache(existing["category"], existing["prompt_key"])

                log_info(f"Prompt updated: {existing['category']}/{existing['prompt_key']} v{new_version}", "prompts_api")
                return success_response(_format_prompt(updated))

            updates = []
            params = []
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            if is_active is not None:
                updates.append("is_active = %s")
                params.append(is_active)
            updates.append("updated_at = NOW()")
            params.append(prompt_id)

            cur.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = %s", params)
            conn.commit()

            cur.execute("SELECT * FROM prompts WHERE id = %s", (prompt_id,))
            updated = cur.fetchone()

            from prompts import prompt_loader
            prompt_loader.invalidate_cache(existing["category"], existing["prompt_key"])

            return success_response(_format_prompt(updated))
        finally:
            cur.close()
            conn.close()

    except Exception as e:
        log_error(f"Failed to update prompt: {e}", "prompts_api")
        return {"success": False, "error": str(e)}


@router.get("/prompts-categories")
async def get_categories(http_request: Request):
    try:
        user = get_current_user(http_request)
        if not user:
            return {"success": False, "error": "Unauthorized"}

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT category, COUNT(*) as count,
                       COUNT(*) FILTER (WHERE is_active) as active_count
                FROM prompts
                GROUP BY category
                ORDER BY category
            """)
            categories = [
                {"name": row["category"], "count": row["count"], "activeCount": row["active_count"]}
                for row in cur.fetchall()
            ]
            return success_response(categories)
        finally:
            cur.close()
            conn.close()

    except Exception as e:
        log_error(f"Failed to get categories: {e}", "prompts_api")
        return {"success": False, "error": str(e)}
