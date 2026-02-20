"""User-project membership API router."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.v1.auth import require_auth, require_admin
from repositories.user_project_repository import (
    add_user_to_project, remove_user_from_project,
    get_user_projects, get_project_members, is_user_in_project
)

router = APIRouter(tags=["user-projects"])


class AddMemberRequest(BaseModel):
    user_id: str
    project_id: str
    role: str = "member"


@router.get("/user-projects")
async def get_my_projects(request: Request):
    user = require_auth(request)
    if user["role"] == "admin":
        from core.db.postgres import get_postgres_connection
        import psycopg2.extras
        conn = get_postgres_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]
        finally:
            cur.close()
            conn.close()
    return get_user_projects(user["id"])


@router.get("/projects/{project_id}/members")
async def get_members(project_id: str, request: Request):
    require_auth(request)
    return get_project_members(project_id)


@router.post("/projects/{project_id}/members")
async def add_member(project_id: str, body: AddMemberRequest, request: Request):
    require_admin(request)
    result = add_user_to_project(body.user_id, project_id, body.role)
    return result


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_member(project_id: str, user_id: str, request: Request):
    require_admin(request)
    deleted = remove_user_from_project(user_id, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Membership not found")
    return {"success": True}
