"""Workflow session and artifact API router."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Any
import psycopg2.extras

from api.v1.auth import require_auth
from core.db.postgres import get_postgres_connection
from repositories.session_repository import (
    create_workflow_session, get_active_session, set_active_session,
    list_sessions, save_artifact, get_artifact, get_all_artifacts,
    delete_session as delete_workflow_session
)

router = APIRouter(tags=["sessions"])


class CreateSessionRequest(BaseModel):
    project_id: str
    label: Optional[str] = None
    request_type: Optional[str] = None
    feature_title: Optional[str] = None


class SaveArtifactRequest(BaseModel):
    artifact_type: str
    payload: Any


@router.post("/sessions")
async def create_session(body: CreateSessionRequest, request: Request):
    user = require_auth(request)
    session = create_workflow_session(
        user_id=user["id"],
        project_id=body.project_id,
        label=body.label,
        request_type=body.request_type,
        feature_title=body.feature_title,
    )
    return session


@router.get("/sessions/active")
async def get_active(request: Request, project_id: str):
    user = require_auth(request)
    session = get_active_session(user["id"], project_id)
    if not session:
        return {"session": None, "artifacts": {}}
    artifacts = get_all_artifacts(session["id"])
    artifact_map = {a["artifact_type"]: a["payload"] for a in artifacts}
    return {"session": session, "artifacts": artifact_map}


@router.get("/sessions")
async def list_user_sessions(request: Request, project_id: str):
    user = require_auth(request)
    sessions = list_sessions(user["id"], project_id)
    return sessions


@router.post("/sessions/{session_id}/activate")
async def activate_session(session_id: str, request: Request):
    user = require_auth(request)
    session = set_active_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _get_session_project_id(session_id: str, user_id: str) -> str:
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT project_id FROM workflow_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        return row["project_id"]
    finally:
        cur.close()
        conn.close()


@router.post("/sessions/{session_id}/artifacts")
async def save_session_artifact(session_id: str, body: SaveArtifactRequest, request: Request):
    user = require_auth(request)
    project_id = _get_session_project_id(session_id, user["id"])
    artifact = save_artifact(session_id, project_id, body.artifact_type, body.payload)
    return artifact


@router.get("/sessions/{session_id}/artifacts/{artifact_type}")
async def get_session_artifact(session_id: str, artifact_type: str, request: Request):
    require_auth(request)
    artifact = get_artifact(session_id, artifact_type)
    if not artifact:
        return {"payload": None}
    return {"payload": artifact["payload"]}


@router.get("/sessions/{session_id}/artifacts")
async def get_session_artifacts(session_id: str, request: Request):
    require_auth(request)
    artifacts = get_all_artifacts(session_id)
    return {a["artifact_type"]: a["payload"] for a in artifacts}


@router.delete("/sessions/{session_id}")
async def remove_session(session_id: str, request: Request):
    user = require_auth(request)
    deleted = delete_workflow_session(session_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}
