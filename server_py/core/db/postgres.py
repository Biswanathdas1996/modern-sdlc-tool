"""PostgreSQL connection management."""
import os
import psycopg2


NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "")
DATABASE_URL = NEON_DATABASE_URL or os.environ.get("DATABASE_URL", "")


def get_postgres_connection():
    """Get a new PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def init_postgres_database():
    """Initialize PostgreSQL schema (users, sessions, feature access tables)."""
    conn = get_postgres_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_feature_access (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                feature_key TEXT NOT NULL,
                granted BOOLEAN NOT NULL DEFAULT true,
                UNIQUE(user_id, feature_key)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ufa_user ON user_feature_access(user_id);")
        conn.commit()
    finally:
        cur.close()
        conn.close()
