"""Storage manager coordinating all PostgreSQL repositories."""
from typing import Optional, List, Dict, Any
from repositories.pg_repository import (
    ProjectPgRepository,
    _build_analysis_repo,
    _build_documentation_repo,
    _build_bpmn_repo,
    _build_feature_request_repo,
    _build_brd_repo,
    _build_test_case_repo,
    _build_test_data_repo,
    _build_user_story_repo,
    _build_db_schema_repo,
    _build_knowledge_doc_repo,
)


class StorageManager:
    """Central storage manager backed by PostgreSQL."""

    def __init__(self):
        self.projects = ProjectPgRepository()
        self.analyses = _build_analysis_repo()
        self.documentation_repo = _build_documentation_repo()
        self.feature_requests_repo = _build_feature_request_repo()
        self.brds_repo = _build_brd_repo()
        self.test_cases_repo = _build_test_case_repo()
        self.test_data_repo = _build_test_data_repo()
        self.user_stories_repo = _build_user_story_repo()
        self.bpmn_repo = _build_bpmn_repo()
        self.db_schemas_repo = _build_db_schema_repo()
        self.kb_docs_repo = _build_knowledge_doc_repo()

        self.current_project_id: Optional[str] = None
        self.current_feature_request_id: Optional[str] = None
        self.current_brd_id: Optional[str] = None

    def get_project(self, id: str) -> Optional[Dict]:
        return self.projects.get_by_id(id)

    def get_all_projects(self) -> List[Dict]:
        return self.projects.get_all()

    def create_project(self, data: dict) -> Dict:
        project = self.projects.create(data)
        self.current_project_id = project["id"]
        return project

    def update_project(self, id: str, updates: dict) -> Optional[Dict]:
        return self.projects.update(id, updates)

    def delete_project(self, id: str) -> bool:
        return self.projects.delete(id)

    def get_analysis(self, project_id: str) -> Optional[Dict]:
        return self.analyses.get_first_by_field("projectId", project_id)

    def create_analysis(self, data: dict) -> Dict:
        return self.analyses.create(data)

    def get_documentation(self, project_id: str) -> Optional[Dict]:
        return self.documentation_repo.get_first_by_field("projectId", project_id)

    def create_documentation(self, data: dict) -> Dict:
        return self.documentation_repo.create(data)

    def update_documentation(self, project_id: str, updates: dict) -> Optional[Dict]:
        existing = self.get_documentation(project_id)
        if not existing:
            return None
        return self.documentation_repo.update(existing["id"], updates)

    def get_feature_request(self, id: str) -> Optional[Dict]:
        return self.feature_requests_repo.get_by_id(id)

    def get_feature_requests_by_project(self, project_id: str) -> List[Dict]:
        return self.feature_requests_repo.get_by_project(project_id)

    def create_feature_request(self, data: dict) -> Dict:
        request = self.feature_requests_repo.create(data)
        self.current_feature_request_id = request["id"]
        return request

    def get_current_feature_request(self) -> Optional[Dict]:
        if not self.current_feature_request_id:
            return None
        return self.feature_requests_repo.get_by_id(self.current_feature_request_id)

    def get_brd(self, id: str) -> Optional[Dict]:
        return self.brds_repo.get_by_id(id)

    def get_brds_by_project(self, project_id: str) -> List[Dict]:
        return self.brds_repo.get_by_project(project_id)

    def create_brd(self, data: dict) -> Dict:
        brd = self.brds_repo.create(data)
        self.current_brd_id = brd["id"]
        return brd

    def update_brd(self, id: str, updates: dict) -> Optional[Dict]:
        return self.brds_repo.update(id, updates)

    def get_current_brd(self, project_id: str = None, user_id: str = None) -> Optional[Dict]:
        if project_id:
            if user_id:
                brds = self.brds_repo.get_by_fields({"projectId": project_id, "createdBy": user_id})
                if brds:
                    return brds[0]
            brds = self.brds_repo.get_by_project(project_id)
            return brds[0] if brds else None
        if not self.current_brd_id:
            return None
        return self.brds_repo.get_by_id(self.current_brd_id)

    def get_test_cases(self, brd_id: str) -> List[Dict]:
        return self.test_cases_repo.get_by_field("brdId", brd_id)

    def get_test_cases_by_project(self, project_id: str) -> List[Dict]:
        return self.test_cases_repo.get_by_project(project_id)

    def create_test_case(self, data: dict) -> Dict:
        return self.test_cases_repo.create(data)

    def create_test_cases(self, test_cases: list) -> List[Dict]:
        return [self.create_test_case(tc) for tc in test_cases]

    def get_all_test_data(self) -> List[Dict]:
        return self.test_data_repo.get_all()

    def get_test_data_by_project(self, project_id: str) -> List[Dict]:
        return self.test_data_repo.get_by_project(project_id)

    def get_test_data_by_brd(self, brd_id: str) -> List[Dict]:
        test_cases = self.get_test_cases(brd_id)
        if not test_cases:
            return []
        result = []
        for tc in test_cases:
            tc_data = self.test_data_repo.get_by_field("testCaseId", tc.get("id", ""))
            result.extend(tc_data)
        return result

    def create_test_data(self, data: dict) -> Dict:
        valid_types = {"valid", "invalid", "edge", "boundary"}
        raw_type = str(data.get("dataType", "valid")).lower().strip()
        if raw_type not in valid_types:
            data = {**data, "dataType": "valid"}
        return self.test_data_repo.create(data)

    def create_test_data_batch(self, data_list: list) -> List[Dict]:
        return [self.create_test_data(d) for d in data_list]

    def get_user_stories(self, brd_id: str) -> List[Dict]:
        return self.user_stories_repo.get_by_field("brdId", brd_id)

    def get_user_stories_by_project(self, project_id: str) -> List[Dict]:
        return self.user_stories_repo.get_by_project(project_id)

    def create_user_story(self, data: dict) -> Dict:
        return self.user_stories_repo.create(data)

    def create_user_stories(self, stories: list) -> List[Dict]:
        return [self.create_user_story(s) for s in stories]

    def update_user_story(self, id: str, updates: dict) -> Optional[Dict]:
        return self.user_stories_repo.update(id, updates)

    def delete_user_story(self, id: str) -> bool:
        return self.user_stories_repo.delete(id)

    def get_bpmn_diagram(self, documentation_id: str) -> Optional[Dict]:
        return self.bpmn_repo.get_first_by_field("documentationId", documentation_id)

    def create_bpmn_diagram(self, data: dict) -> Dict:
        return self.bpmn_repo.create(data)

    def delete_bpmn_diagram(self, documentation_id: str) -> int:
        return self.bpmn_repo.delete_by_field("documentationId", documentation_id)

    def get_database_schema(self, project_id: str) -> Optional[Dict]:
        return self.db_schemas_repo.get_first_by_field("projectId", project_id)

    def create_database_schema(self, data: dict) -> Dict:
        return self.db_schemas_repo.create(data)

    def delete_database_schema(self, project_id: str) -> int:
        return self.db_schemas_repo.delete_by_field("projectId", project_id)

    def get_knowledge_documents(self, project_id: str) -> List[Dict]:
        return self.kb_docs_repo.get_by_project(project_id)

    def create_knowledge_document(self, data: dict) -> Dict:
        return self.kb_docs_repo.create(data)


storage = StorageManager()
