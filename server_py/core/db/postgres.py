"""PostgreSQL connection management."""
import os
import psycopg2
from psycopg2.extras import RealDictCursor


NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "")
DATABASE_URL = NEON_DATABASE_URL or os.environ.get("DATABASE_URL", "")


def get_postgres_connection():
    """Get a new PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def get_dict_connection():
    """Get a PostgreSQL connection with RealDictCursor for dict-like rows."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_postgres_database():
    """Initialize PostgreSQL schema for all tables."""
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                repo_url TEXT NOT NULL DEFAULT '',
                description TEXT,
                tech_stack JSONB NOT NULL DEFAULT '[]'::jsonb,
                analyzed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_projects (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, project_id)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflow_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                label TEXT,
                request_type TEXT,
                feature_title TEXT,
                is_active BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_artifacts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES workflow_sessions(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                artifact_type TEXT NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(session_id, artifact_type)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS repo_analyses (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                summary TEXT NOT NULL DEFAULT '',
                architecture TEXT NOT NULL DEFAULT '',
                features JSONB NOT NULL DEFAULT '[]'::jsonb,
                tech_stack JSONB NOT NULL DEFAULT '{}'::jsonb,
                testing_framework TEXT,
                code_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS documentation (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                sections JSONB NOT NULL DEFAULT '[]'::jsonb,
                database_schema JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bpmn_diagrams (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                documentation_id TEXT NOT NULL,
                diagrams JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS feature_requests (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                input_type TEXT NOT NULL DEFAULT 'text',
                request_type TEXT NOT NULL DEFAULT 'feature',
                raw_input TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS brds (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                feature_request_id TEXT NOT NULL,
                request_type TEXT NOT NULL DEFAULT 'feature',
                title TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0',
                status TEXT NOT NULL DEFAULT 'draft',
                source_documentation TEXT,
                knowledge_sources JSONB,
                content JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_cases (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                brd_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'happy_path',
                type TEXT NOT NULL DEFAULT 'unit',
                priority TEXT NOT NULL DEFAULT 'medium',
                preconditions JSONB NOT NULL DEFAULT '[]'::jsonb,
                steps JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_outcome TEXT NOT NULL DEFAULT '',
                code_snippet TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_data (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                test_case_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                data_type TEXT NOT NULL DEFAULT 'valid',
                data JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_stories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                brd_id TEXT NOT NULL,
                story_key TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                as_a TEXT NOT NULL DEFAULT '',
                i_want TEXT NOT NULL DEFAULT '',
                so_that TEXT NOT NULL DEFAULT '',
                acceptance_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
                priority TEXT NOT NULL DEFAULT 'medium',
                story_points INTEGER,
                labels JSONB NOT NULL DEFAULT '[]'::jsonb,
                epic TEXT,
                related_requirement_id TEXT,
                technical_notes TEXT,
                dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
                jira_key TEXT,
                parent_jira_key TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS database_schemas (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                connection_string TEXT NOT NULL DEFAULT '',
                database_name TEXT NOT NULL DEFAULT '',
                tables JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'processing',
                error_message TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ufa_user ON user_feature_access(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_projects_user ON user_projects(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_projects_project ON user_projects(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_workflow_sessions_user ON workflow_sessions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_workflow_sessions_project ON workflow_sessions(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_workflow_sessions_active ON workflow_sessions(user_id, project_id, is_active);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_session_artifacts_session ON session_artifacts(session_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_session_artifacts_type ON session_artifacts(session_id, artifact_type);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_repo_analyses_project ON repo_analyses(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documentation_project ON documentation(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bpmn_project ON bpmn_diagrams(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bpmn_doc ON bpmn_diagrams(documentation_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feature_requests_project ON feature_requests(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_brds_project ON brds(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_brds_feature_request ON brds(feature_request_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_project ON test_cases(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_brd ON test_cases(brd_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_test_data_project ON test_data(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_test_data_test_case ON test_data(test_case_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stories_project ON user_stories(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stories_brd ON user_stories(brd_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_db_schemas_project ON database_schemas(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_docs_project ON knowledge_documents(project_id);")
        conn.commit()
    finally:
        cur.close()
        conn.close()
