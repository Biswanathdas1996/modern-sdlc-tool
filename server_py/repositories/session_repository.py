"""Workflow session and artifact persistence."""
import uuid
import json
from typing import Optional, List, Dict, Any
import psycopg2
import psycopg2.extras
from core.db.postgres import get_postgres_connection


def create_workflow_session(user_id: str, project_id: str, label: str = None, request_type: str = None, feature_title: str = None) -> Dict[str, Any]:
    """Create a new workflow session and mark it as active (deactivating others for this user+project)."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        cur.execute(
            "UPDATE workflow_sessions SET is_active = false WHERE user_id = %s AND project_id = %s AND is_active = true",
            (user_id, project_id)
        )
        cur.execute(
            """INSERT INTO workflow_sessions (id, user_id, project_id, label, request_type, feature_title, is_active, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, true, NOW()) RETURNING *""",
            (session_id, user_id, project_id, label, request_type, feature_title)
        )
        session = dict(cur.fetchone())
        conn.commit()
        return session
    finally:
        cur.close()
        conn.close()


def get_active_session(user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """Get the currently active session for a user+project."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM workflow_sessions WHERE user_id = %s AND project_id = %s AND is_active = true ORDER BY created_at DESC LIMIT 1",
            (user_id, project_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def set_active_session(session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Set a specific session as active (deactivating others for same user+project)."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM workflow_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
        session = cur.fetchone()
        if not session:
            return None
        session = dict(session)
        cur.execute(
            "UPDATE workflow_sessions SET is_active = false WHERE user_id = %s AND project_id = %s AND is_active = true",
            (user_id, session["project_id"])
        )
        cur.execute(
            "UPDATE workflow_sessions SET is_active = true WHERE id = %s RETURNING *",
            (session_id,)
        )
        result = dict(cur.fetchone())
        conn.commit()
        return result
    finally:
        cur.close()
        conn.close()


def list_sessions(user_id: str, project_id: str) -> List[Dict[str, Any]]:
    """List all sessions for a user+project."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM workflow_sessions WHERE user_id = %s AND project_id = %s ORDER BY created_at DESC",
            (user_id, project_id)
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def save_artifact(session_id: str, project_id: str, artifact_type: str, payload: Any) -> Dict[str, Any]:
    """Save or update a session artifact (upsert)."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """INSERT INTO session_artifacts (id, session_id, project_id, artifact_type, payload, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
               ON CONFLICT (session_id, artifact_type)
               DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
               RETURNING *""",
            (artifact_id, session_id, project_id, artifact_type, json.dumps(payload))
        )
        result = dict(cur.fetchone())
        conn.commit()
        return result
    finally:
        cur.close()
        conn.close()


def get_artifact(session_id: str, artifact_type: str) -> Optional[Dict[str, Any]]:
    """Get a specific artifact from a session."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM session_artifacts WHERE session_id = %s AND artifact_type = %s",
            (session_id, artifact_type)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def get_all_artifacts(session_id: str) -> List[Dict[str, Any]]:
    """Get all artifacts for a session."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM session_artifacts WHERE session_id = %s ORDER BY artifact_type",
            (session_id,)
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def delete_session(session_id: str, user_id: str) -> bool:
    """Delete a workflow session and its artifacts."""
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM workflow_sessions WHERE id = %s AND user_id = %s",
            (session_id, user_id)
        )
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        cur.close()
        conn.close()
