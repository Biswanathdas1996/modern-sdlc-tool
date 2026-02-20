"""Service for restoring session data from client-side storage."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from repositories import storage
from core.logging import log_info


def restore_feature_request(fr_data: Optional[Dict[str, Any]]):
    """Restore a feature request from session data if not in storage."""
    feature_request = storage.get_current_feature_request()
    if feature_request:
        return feature_request

    if not fr_data:
        return None

    fr_data.setdefault("id", "restored")
    fr_data.setdefault("projectId", "global")
    fr_data.setdefault("inputType", "text")
    fr_data.setdefault("requestType", "feature")
    fr_data.setdefault("createdAt", datetime.now().isoformat())

    feature_request = storage.create_feature_request(fr_data)
    storage.current_feature_request_id = feature_request["id"]
    log_info("Feature request restored from session", "session")
    return feature_request


def restore_brd(brd_data: Optional[Dict[str, Any]]):
    """Restore a BRD from session data if not in storage."""
    brd = storage.get_current_brd()
    if brd:
        return brd

    if not brd_data:
        return None

    brd_data.setdefault("id", "restored")
    brd_data.setdefault("requestType", "feature")
    brd_data.setdefault("version", "1.0")
    brd_data.setdefault("status", "draft")
    brd_data.setdefault("createdAt", datetime.now().isoformat())
    brd_data.setdefault("updatedAt", datetime.now().isoformat())

    brd = storage.create_brd(brd_data)
    log_info("BRD restored from session", "session")
    return brd


def restore_analysis(analysis_data: Optional[Dict[str, Any]]):
    """Restore repo analysis from session data if not in storage."""
    projects = storage.get_all_projects()
    if projects:
        analysis = storage.get_analysis(projects[0]["id"])
        if analysis:
            return analysis

    if not analysis_data:
        return None

    return analysis_data


def restore_documentation(doc_data: Optional[Dict[str, Any]]):
    """Restore documentation from session data if not in storage."""
    projects = storage.get_all_projects()
    if projects:
        doc = storage.get_documentation(projects[0]["id"])
        if doc:
            return doc

    if not doc_data:
        return None

    return doc_data


def restore_database_schema(schema_data: Optional[Dict[str, Any]]):
    """Restore database schema from session data if not in storage."""
    projects = storage.get_all_projects()
    if projects:
        schema = storage.get_database_schema(projects[0]["id"])
        if schema:
            return schema

    if not schema_data:
        return None

    return schema_data


def restore_test_cases(test_cases_data: Optional[List[Dict[str, Any]]], brd_id: str):
    """Restore test cases from session data if not in storage."""
    existing = storage.get_test_cases(brd_id)
    if existing:
        return existing

    if not test_cases_data:
        return []

    return storage.create_test_cases(test_cases_data)


def restore_user_stories(stories_data: Optional[List[Dict[str, Any]]], brd_id: str):
    """Restore user stories from session data if not in storage."""
    existing = storage.get_user_stories(brd_id)
    if existing:
        return existing

    if not stories_data:
        return []

    return storage.create_user_stories(stories_data)


def get_project_context():
    """Get common project context (project_id, analysis, documentation, database_schema)."""
    projects = storage.get_all_projects()
    project_id = projects[0]["id"] if projects else "global"
    analysis = storage.get_analysis(project_id) if projects else None
    documentation = storage.get_documentation(project_id) if projects else None
    database_schema = storage.get_database_schema(project_id) if projects else None
    return project_id, analysis, documentation, database_schema
