"""PostgreSQL-backed repository for all domain entities."""
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.db.postgres import get_postgres_connection
from psycopg2.extras import RealDictCursor


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _gen_id() -> str:
    return str(uuid.uuid4())


def _json_dumps(obj):
    if obj is None:
        return None
    return json.dumps(obj)


def _json_loads(val):
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    return json.loads(val)


class ProjectPgRepository:
    """PostgreSQL repository for projects."""

    def get_all(self) -> List[Dict]:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [self._to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_id(self, project_id: str) -> Optional[Dict]:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            row = cur.fetchone()
            return self._to_dict(row) if row else None
        finally:
            conn.close()

    def create(self, data: Dict) -> Dict:
        pid = data.get("id") or _gen_id()
        now = _now_iso()
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                INSERT INTO projects (id, name, repo_url, description, tech_stack, analyzed_at, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (
                pid,
                data.get("name", ""),
                data.get("repoUrl", data.get("repo_url", "")),
                data.get("description"),
                _json_dumps(data.get("techStack", data.get("tech_stack", []))),
                data.get("analyzedAt", data.get("analyzed_at", now)),
                data.get("status", "pending"),
                now,
            ))
            row = cur.fetchone()
            conn.commit()
            return self._to_dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update(self, project_id: str, updates: Dict) -> Optional[Dict]:
        field_map = {
            "name": "name",
            "repoUrl": "repo_url",
            "repo_url": "repo_url",
            "description": "description",
            "techStack": "tech_stack",
            "tech_stack": "tech_stack",
            "status": "status",
        }
        sets = []
        vals = []
        for key, val in updates.items():
            col = field_map.get(key)
            if col:
                if col == "tech_stack":
                    sets.append(f"{col} = %s")
                    vals.append(_json_dumps(val))
                else:
                    sets.append(f"{col} = %s")
                    vals.append(val)
        if not sets:
            return self.get_by_id(project_id)
        vals.append(project_id)
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = %s RETURNING *", vals)
            row = cur.fetchone()
            conn.commit()
            return self._to_dict(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete(self, project_id: str) -> bool:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _to_dict(self, row) -> Dict:
        if not row:
            return {}
        return {
            "id": row["id"],
            "name": row["name"],
            "repoUrl": row["repo_url"],
            "description": row.get("description"),
            "techStack": _json_loads(row.get("tech_stack", "[]")),
            "analyzedAt": row["analyzed_at"].isoformat() if hasattr(row["analyzed_at"], "isoformat") else str(row["analyzed_at"]),
            "status": row["status"],
        }


class GenericPgRepository:
    """Generic PostgreSQL repository for domain entities with JSONB storage."""

    def __init__(self, table: str, field_map: Dict[str, str], json_fields: set = None):
        self.table = table
        self.field_map = field_map
        self.json_fields = json_fields or set()

    def get_by_id(self, entity_id: str) -> Optional[Dict]:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"SELECT * FROM {self.table} WHERE id = %s", (entity_id,))
            row = cur.fetchone()
            return self._to_dict(row) if row else None
        finally:
            conn.close()

    def get_by_project(self, project_id: str) -> List[Dict]:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"SELECT * FROM {self.table} WHERE project_id = %s ORDER BY created_at DESC", (project_id,))
            return [self._to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_by_field(self, field_name: str, value: str) -> List[Dict]:
        col = self.field_map.get(field_name, field_name)
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"SELECT * FROM {self.table} WHERE {col} = %s ORDER BY created_at DESC", (value,))
            return [self._to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_first_by_field(self, field_name: str, value: str) -> Optional[Dict]:
        results = self.get_by_field(field_name, value)
        return results[0] if results else None

    def get_by_fields(self, filters: Dict[str, str]) -> List[Dict]:
        """Query by multiple field=value pairs (AND logic)."""
        conditions = []
        values = []
        for camel_key, val in filters.items():
            col = self.field_map.get(camel_key, camel_key)
            conditions.append(f"{col} = %s")
            values.append(val)
        where = " AND ".join(conditions)
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"SELECT * FROM {self.table} WHERE {where} ORDER BY created_at DESC", values)
            return [self._to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_all(self) -> List[Dict]:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"SELECT * FROM {self.table} ORDER BY created_at DESC")
            return [self._to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def create(self, data: Dict) -> Dict:
        eid = data.get("id") or _gen_id()
        now = _now_iso()
        cols = ["id"]
        vals = [eid]
        placeholders = ["%s"]

        for camel_key, db_col in self.field_map.items():
            if camel_key == "id":
                continue
            val = data.get(camel_key)
            if val is None and db_col in ("created_at", "updated_at"):
                val = now
            if val is not None:
                cols.append(db_col)
                if db_col in self.json_fields:
                    vals.append(_json_dumps(val))
                else:
                    vals.append(val)
                placeholders.append("%s")

        if "created_at" not in cols and "createdAt" not in data:
            cols.append("created_at")
            vals.append(now)
            placeholders.append("%s")

        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            sql = f"INSERT INTO {self.table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *"
            cur.execute(sql, vals)
            row = cur.fetchone()
            conn.commit()
            return self._to_dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update(self, entity_id: str, updates: Dict) -> Optional[Dict]:
        sets = []
        vals = []
        for camel_key, val in updates.items():
            db_col = self.field_map.get(camel_key)
            if db_col and db_col != "id":
                if db_col in self.json_fields:
                    sets.append(f"{db_col} = %s")
                    vals.append(_json_dumps(val))
                else:
                    sets.append(f"{db_col} = %s")
                    vals.append(val)

        if "updated_at" in [v for v in self.field_map.values()]:
            sets.append("updated_at = %s")
            vals.append(_now_iso())

        if not sets:
            return self.get_by_id(entity_id)

        vals.append(entity_id)
        conn = get_postgres_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"UPDATE {self.table} SET {', '.join(sets)} WHERE id = %s RETURNING *", vals)
            row = cur.fetchone()
            conn.commit()
            return self._to_dict(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete(self, entity_id: str) -> bool:
        conn = get_postgres_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {self.table} WHERE id = %s", (entity_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_by_field(self, field_name: str, value: str) -> int:
        col = self.field_map.get(field_name, field_name)
        conn = get_postgres_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {self.table} WHERE {col} = %s", (value,))
            count = cur.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _to_dict(self, row) -> Dict:
        if not row:
            return {}
        reverse_map = {v: k for k, v in self.field_map.items()}
        result = {}
        for db_col, val in row.items():
            camel_key = reverse_map.get(db_col, db_col)
            if db_col in self.json_fields:
                result[camel_key] = _json_loads(val)
            elif hasattr(val, "isoformat"):
                result[camel_key] = val.isoformat()
            else:
                result[camel_key] = val
        return result


def _build_analysis_repo():
    return GenericPgRepository(
        table="repo_analyses",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "summary": "summary",
            "architecture": "architecture",
            "features": "features",
            "techStack": "tech_stack",
            "testingFramework": "testing_framework",
            "codePatterns": "code_patterns",
            "createdAt": "created_at",
        },
        json_fields={"features", "tech_stack", "code_patterns"},
    )


def _build_documentation_repo():
    return GenericPgRepository(
        table="documentation",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "title": "title",
            "content": "content",
            "sections": "sections",
            "databaseSchema": "database_schema",
            "createdAt": "created_at",
        },
        json_fields={"sections", "database_schema"},
    )


def _build_bpmn_repo():
    return GenericPgRepository(
        table="bpmn_diagrams",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "documentationId": "documentation_id",
            "diagrams": "diagrams",
            "createdAt": "created_at",
        },
        json_fields={"diagrams"},
    )


def _build_feature_request_repo():
    return GenericPgRepository(
        table="feature_requests",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "title": "title",
            "description": "description",
            "inputType": "input_type",
            "requestType": "request_type",
            "rawInput": "raw_input",
            "createdBy": "created_by",
            "createdAt": "created_at",
        },
        json_fields=set(),
    )


def _build_brd_repo():
    return GenericPgRepository(
        table="brds",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "featureRequestId": "feature_request_id",
            "requestType": "request_type",
            "title": "title",
            "version": "version",
            "status": "status",
            "sourceDocumentation": "source_documentation",
            "knowledgeSources": "knowledge_sources",
            "content": "content",
            "createdBy": "created_by",
            "createdAt": "created_at",
            "updatedAt": "updated_at",
        },
        json_fields={"knowledge_sources", "content"},
    )


def _build_test_case_repo():
    return GenericPgRepository(
        table="test_cases",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "brdId": "brd_id",
            "requirementId": "requirement_id",
            "title": "title",
            "description": "description",
            "category": "category",
            "type": "type",
            "priority": "priority",
            "preconditions": "preconditions",
            "steps": "steps",
            "expectedOutcome": "expected_outcome",
            "codeSnippet": "code_snippet",
            "createdAt": "created_at",
        },
        json_fields={"preconditions", "steps"},
    )


def _build_test_data_repo():
    return GenericPgRepository(
        table="test_data",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "testCaseId": "test_case_id",
            "name": "name",
            "description": "description",
            "dataType": "data_type",
            "data": "data",
            "createdAt": "created_at",
        },
        json_fields={"data"},
    )


def _build_user_story_repo():
    return GenericPgRepository(
        table="user_stories",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "brdId": "brd_id",
            "storyKey": "story_key",
            "title": "title",
            "description": "description",
            "asA": "as_a",
            "iWant": "i_want",
            "soThat": "so_that",
            "acceptanceCriteria": "acceptance_criteria",
            "priority": "priority",
            "storyPoints": "story_points",
            "labels": "labels",
            "epic": "epic",
            "relatedRequirementId": "related_requirement_id",
            "technicalNotes": "technical_notes",
            "dependencies": "dependencies",
            "jiraKey": "jira_key",
            "parentJiraKey": "parent_jira_key",
            "createdAt": "created_at",
        },
        json_fields={"acceptance_criteria", "labels", "dependencies"},
    )


def _build_db_schema_repo():
    return GenericPgRepository(
        table="database_schemas",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "connectionString": "connection_string",
            "databaseName": "database_name",
            "tables": "tables",
            "createdAt": "created_at",
            "updatedAt": "updated_at",
        },
        json_fields={"tables"},
    )


def _build_knowledge_doc_repo():
    return GenericPgRepository(
        table="knowledge_documents",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "filename": "filename",
            "originalName": "original_name",
            "contentType": "content_type",
            "size": "size",
            "chunkCount": "chunk_count",
            "status": "status",
            "errorMessage": "error_message",
            "createdAt": "created_at",
        },
        json_fields=set(),
    )


def _build_rag_evaluation_repo():
    return GenericPgRepository(
        table="rag_evaluations",
        field_map={
            "id": "id",
            "projectId": "project_id",
            "featureRequestId": "feature_request_id",
            "brdId": "brd_id",
            "featureTitle": "feature_title",
            "status": "status",
            "faithfulness": "faithfulness",
            "answerRelevancy": "answer_relevancy",
            "contextRelevancy": "context_relevancy",
            "contextPrecision": "context_precision",
            "hallucinationScore": "hallucination_score",
            "overallScore": "overall_score",
            "contextChunksCount": "context_chunks_count",
            "avgChunkScore": "avg_chunk_score",
            "modelUsed": "model_used",
            "evaluationDetails": "evaluation_details",
            "errorMessage": "error_message",
            "createdAt": "created_at",
            "completedAt": "completed_at",
        },
        json_fields={"evaluation_details"},
    )
