"""User-project membership persistence."""
import uuid
from typing import List, Dict, Any
import psycopg2
import psycopg2.extras
from core.db.postgres import get_postgres_connection


def add_user_to_project(user_id: str, project_id: str, role: str = "member") -> Dict[str, Any]:
    """Add a user to a project."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        membership_id = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO user_projects (id, user_id, project_id, role, created_at)
               VALUES (%s, %s, %s, %s, NOW())
               ON CONFLICT (user_id, project_id) DO UPDATE SET role = EXCLUDED.role
               RETURNING *""",
            (membership_id, user_id, project_id, role)
        )
        result = dict(cur.fetchone())
        conn.commit()
        return result
    finally:
        cur.close()
        conn.close()


def remove_user_from_project(user_id: str, project_id: str) -> bool:
    """Remove a user from a project."""
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM user_projects WHERE user_id = %s AND project_id = %s",
            (user_id, project_id)
        )
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        cur.close()
        conn.close()


def _project_to_camel(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw project DB row to camelCase dict matching frontend schema."""
    import json
    result = {
        "id": row["id"],
        "name": row["name"],
        "repoUrl": row.get("repo_url", ""),
        "description": row.get("description"),
        "techStack": json.loads(row["tech_stack"]) if isinstance(row.get("tech_stack"), str) else (row.get("tech_stack") or []),
        "analyzedAt": row["analyzed_at"].isoformat() if hasattr(row.get("analyzed_at"), "isoformat") else str(row.get("analyzed_at", "")),
        "status": row.get("status", "pending"),
    }
    if "membership_role" in row:
        result["membershipRole"] = row["membership_role"]
    return result


def get_user_projects(user_id: str) -> List[Dict[str, Any]]:
    """Get all projects a user belongs to."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT p.*, up.role as membership_role
               FROM projects p
               JOIN user_projects up ON p.id = up.project_id
               WHERE up.user_id = %s
               ORDER BY p.created_at DESC""",
            (user_id,)
        )
        return [_project_to_camel(dict(row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def get_project_members(project_id: str) -> List[Dict[str, Any]]:
    """Get all users in a project."""
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT u.id, u.username, u.email, u.role, u.is_active, up.role as membership_role, up.created_at as joined_at
               FROM users u
               JOIN user_projects up ON u.id = up.user_id
               WHERE up.project_id = %s
               ORDER BY up.created_at DESC""",
            (project_id,)
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def is_user_in_project(user_id: str, project_id: str) -> bool:
    """Check if a user belongs to a project."""
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s",
            (user_id, project_id)
        )
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()
