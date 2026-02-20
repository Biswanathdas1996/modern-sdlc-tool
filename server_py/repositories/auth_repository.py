"""Authentication and user management repository."""
import uuid
import bcrypt
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from core.db.postgres import get_postgres_connection


ALL_FEATURES = [
    {"key": "analyze", "label": "Analyze Repository", "category": "prerequisite"},
    {"key": "documentation", "label": "Documentation", "category": "prerequisite"},
    {"key": "requirements", "label": "Feature Request", "category": "workflow"},
    {"key": "brd", "label": "Generate BRD", "category": "workflow"},
    {"key": "user_stories", "label": "User Stories", "category": "workflow"},
    {"key": "code_generation", "label": "Generate Code", "category": "workflow"},
    {"key": "test_cases", "label": "Test Cases", "category": "workflow"},
    {"key": "test_data", "label": "Test Data", "category": "workflow"},
    {"key": "knowledge_base", "label": "Knowledge Base", "category": "tools"},
    {"key": "agent_jira", "label": "JIRA Agent", "category": "agents"},
    {"key": "agent_security", "label": "Security Agent", "category": "agents"},
    {"key": "agent_unit_test", "label": "Unit Test Agent", "category": "agents"},
    {"key": "agent_web_test", "label": "Web Test Agent", "category": "agents"},
]

ALL_FEATURE_KEYS = [f["key"] for f in ALL_FEATURES]


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def seed_admin_user():
    """Create default admin user if none exists."""
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if cur.fetchone():
            return
        admin_id = str(uuid.uuid4())
        password_hash = _hash_password("admin123")
        cur.execute(
            """INSERT INTO users (id, username, email, password_hash, role, is_active)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (admin_id, "admin", "admin@docugen.ai", password_hash, "admin", True)
        )
        for fk in ALL_FEATURE_KEYS:
            cur.execute(
                """INSERT INTO user_feature_access (id, user_id, feature_key, granted)
                   VALUES (%s, %s, %s, %s)""",
                (str(uuid.uuid4()), admin_id, fk, True)
            )
        conn.commit()
        print(f"[AUTH] Default admin created: admin@docugen.ai / admin123")
    except Exception as e:
        conn.rollback()
        print(f"[AUTH] Error seeding admin: {e}")
    finally:
        cur.close()
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, username, email, password_hash, role, is_active, project_id, created_at FROM users WHERE email = %s AND is_active = true", (email,))
        user = cur.fetchone()
        if not user or not _verify_password(password, user["password_hash"]):
            return None
        return dict(user)
    finally:
        cur.close()
        conn.close()


def create_session(user_id: str, duration_hours: int = 24) -> str:
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
            (session_id, user_id, expires_at)
        )
        conn.commit()
        return session_id
    finally:
        cur.close()
        conn.close()


def get_session_user(session_id: str) -> Optional[Dict[str, Any]]:
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT u.id, u.username, u.email, u.role, u.is_active, u.project_id, u.created_at
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.id = %s AND s.expires_at > NOW() AND u.is_active = true""",
            (session_id,)
        )
        user = cur.fetchone()
        if not user:
            return None
        return dict(user)
    finally:
        cur.close()
        conn.close()


def delete_session(session_id: str):
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_user_permissions(user_id: str) -> List[str]:
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT feature_key FROM user_feature_access WHERE user_id = %s AND granted = true",
            (user_id,)
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def create_user(username: str, email: str, password: str, role: str = "user", features: List[str] = None, project_id: str = None) -> Dict[str, Any]:
    user_id = str(uuid.uuid4())
    pw_hash = _hash_password(password)
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """INSERT INTO users (id, username, email, password_hash, role, is_active, project_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, username, email, role, is_active, project_id, created_at""",
            (user_id, username, email, pw_hash, role, True, project_id)
        )
        user = dict(cur.fetchone())
        granted_features = features if features else []
        for fk in ALL_FEATURE_KEYS:
            cur.execute(
                """INSERT INTO user_feature_access (id, user_id, feature_key, granted)
                   VALUES (%s, %s, %s, %s)""",
                (str(uuid.uuid4()), user_id, fk, fk in granted_features)
            )
        if project_id:
            cur.execute(
                "INSERT INTO user_projects (id, user_id, project_id, role, created_at) VALUES (%s, %s, %s, 'member', NOW())",
                (str(uuid.uuid4()), user_id, project_id)
            )
        conn.commit()
        user["permissions"] = granted_features
        return user
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise ValueError("Username or email already exists")
    finally:
        cur.close()
        conn.close()


def get_all_users() -> List[Dict[str, Any]]:
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT id, username, email, role, is_active, project_id, created_at FROM users ORDER BY created_at DESC"
        )
        users = [dict(row) for row in cur.fetchall()]
        for user in users:
            cur.execute(
                "SELECT feature_key FROM user_feature_access WHERE user_id = %s AND granted = true",
                (user["id"],)
            )
            user["permissions"] = [row["feature_key"] for row in cur.fetchall()]
            cur.execute(
                "SELECT project_id FROM user_projects WHERE user_id = %s",
                (user["id"],)
            )
            user["project_ids"] = [row["project_id"] for row in cur.fetchall()]
        return users
    finally:
        cur.close()
        conn.close()


def update_user_permissions(user_id: str, features: List[str]) -> Dict[str, Any]:
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        for fk in ALL_FEATURE_KEYS:
            cur.execute(
                """INSERT INTO user_feature_access (id, user_id, feature_key, granted)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id, feature_key)
                   DO UPDATE SET granted = %s""",
                (str(uuid.uuid4()), user_id, fk, fk in features, fk in features)
            )
        conn.commit()
        cur.execute(
            "SELECT id, username, email, role, is_active, project_id, created_at FROM users WHERE id = %s",
            (user_id,)
        )
        user = dict(cur.fetchone())
        user["permissions"] = features
        return user
    finally:
        cur.close()
        conn.close()


def update_user_status(user_id: str, is_active: bool) -> Dict[str, Any]:
    conn = get_postgres_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "UPDATE users SET is_active = %s, updated_at = NOW() WHERE id = %s RETURNING id, username, email, role, is_active, project_id, created_at",
            (is_active, user_id)
        )
        user = cur.fetchone()
        if not user:
            raise ValueError("User not found")
        conn.commit()
        user = dict(user)
        cur.execute(
            "SELECT feature_key FROM user_feature_access WHERE user_id = %s AND granted = true",
            (user_id,)
        )
        user["permissions"] = [row["feature_key"] for row in cur.fetchall()]
        return user
    finally:
        cur.close()
        conn.close()


def delete_user(user_id: str):
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("User not found")
        if row[0] == "admin":
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = true")
            count = cur.fetchone()[0]
            if count <= 1:
                raise ValueError("Cannot delete the last admin user")
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def update_user_password(user_id: str, new_password: str):
    pw_hash = _hash_password(new_password)
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s",
            (pw_hash, user_id)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def cleanup_expired_sessions():
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM sessions WHERE expires_at < NOW()")
        conn.commit()
    finally:
        cur.close()
        conn.close()
