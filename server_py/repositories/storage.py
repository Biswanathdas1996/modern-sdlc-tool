"""Storage manager coordinating all repositories."""
from typing import Optional
from repositories.base import BaseRepository
from repositories.project_repository import ProjectRepository
from schemas.entities import (
    Project, RepoAnalysis, Documentation, FeatureRequest, BRD,
    TestCase, TestData, UserStory, BPMNDiagram, DatabaseSchemaInfo,
    KnowledgeDocument
)


class StorageManager:
    """Central storage manager for all entities."""
    
    def __init__(self):
        # Repositories
        self.projects = ProjectRepository()
        self.analyses = BaseRepository(RepoAnalysis)
        self.documentation = BaseRepository(Documentation)
        self.feature_requests = BaseRepository(FeatureRequest)
        self.brds = BaseRepository(BRD)
        self.test_cases = BaseRepository(TestCase)
        self.test_data = BaseRepository(TestData)
        self.user_stories = BaseRepository(UserStory)
        self.bpmn_diagrams = BaseRepository(BPMNDiagram)
        self.database_schemas = BaseRepository(DatabaseSchemaInfo)
        self.knowledge_documents = BaseRepository(KnowledgeDocument)
        
        # Current selections
        self.current_project_id: Optional[str] = None
        self.current_feature_request_id: Optional[str] = None
        self.current_brd_id: Optional[str] = None
        
    # Project methods
    def get_project(self, id: str) -> Optional[Project]:
        return self.projects.get_by_id(id)
        
    def get_all_projects(self):
        return self.projects.get_all_sorted()
        
    def create_project(self, data: dict) -> Project:
        project = self.projects.create(data)
        self.current_project_id = project.id
        return project
        
    def update_project(self, id: str, updates: dict) -> Optional[Project]:
        return self.projects.update(id, updates)
        
    def delete_project(self, id: str):
        self.projects.delete(id)
        
    # Analysis methods
    def get_analysis(self, project_id: str) -> Optional[RepoAnalysis]:
        for analysis in self.analyses.get_all():
            if analysis.projectId == project_id:
                return analysis
        return None
        
    def create_analysis(self, data: dict) -> RepoAnalysis:
        return self.analyses.create(data)
        
    # Documentation methods
    def get_documentation(self, project_id: str) -> Optional[Documentation]:
        for doc in self.documentation.get_all():
            if doc.projectId == project_id:
                return doc
        return None
        
    def create_documentation(self, data: dict) -> Documentation:
        return self.documentation.create(data)
        
    def update_documentation(self, project_id: str, updates: dict) -> Optional[Documentation]:
        existing = self.get_documentation(project_id)
        if not existing:
            return None
        return self.documentation.update(existing.id, updates)
        
    # Feature request methods
    def get_feature_request(self, id: str) -> Optional[FeatureRequest]:
        return self.feature_requests.get_by_id(id)
        
    def get_feature_requests_by_project(self, project_id: str):
        return [r for r in self.feature_requests.get_all() if r.projectId == project_id]
        
    def create_feature_request(self, data: dict) -> FeatureRequest:
        request = self.feature_requests.create(data)
        self.current_feature_request_id = request.id
        return request
        
    def get_current_feature_request(self) -> Optional[FeatureRequest]:
        if not self.current_feature_request_id:
            return None
        return self.feature_requests.get_by_id(self.current_feature_request_id)
        
    # BRD methods
    def get_brd(self, id: str) -> Optional[BRD]:
        return self.brds.get_by_id(id)
        
    def create_brd(self, data: dict) -> BRD:
        brd = self.brds.create(data)
        self.current_brd_id = brd.id
        return brd
        
    def update_brd(self, id: str, updates: dict) -> Optional[BRD]:
        return self.brds.update(id, updates)
        
    def get_current_brd(self) -> Optional[BRD]:
        if not self.current_brd_id:
            return None
        return self.brds.get_by_id(self.current_brd_id)
        
    # Test case methods
    def get_test_cases(self, brd_id: str):
        return [tc for tc in self.test_cases.get_all() if tc.brdId == brd_id]
        
    def create_test_case(self, data: dict) -> TestCase:
        return self.test_cases.create(data)
        
    def create_test_cases(self, test_cases: list):
        return [self.create_test_case(tc) for tc in test_cases]
        
    # Test data methods
    def get_all_test_data(self):
        return self.test_data.get_all()
        
    def create_test_data(self, data: dict) -> TestData:
        return self.test_data.create(data)
        
    def create_test_data_batch(self, data_list: list):
        return [self.create_test_data(d) for d in data_list]
        
    # User story methods
    def get_user_stories(self, brd_id: str):
        return [s for s in self.user_stories.get_all() if s.brdId == brd_id]
        
    def create_user_story(self, data: dict) -> UserStory:
        return self.user_stories.create(data)
        
    def create_user_stories(self, stories: list):
        return [self.create_user_story(s) for s in stories]
        
    def update_user_story(self, id: str, updates: dict) -> Optional[UserStory]:
        return self.user_stories.update(id, updates)
        
    def delete_user_story(self, id: str) -> bool:
        return self.user_stories.delete(id)
        
    # BPMN diagram methods
    def get_bpmn_diagram(self, documentation_id: str) -> Optional[BPMNDiagram]:
        for diagram in self.bpmn_diagrams.get_all():
            if diagram.documentationId == documentation_id:
                return diagram
        return None
        
    def create_bpmn_diagram(self, data: dict) -> BPMNDiagram:
        return self.bpmn_diagrams.create(data)
        
    def delete_bpmn_diagram(self, documentation_id: str):
        to_delete = [
            d.id for d in self.bpmn_diagrams.get_all() 
            if d.documentationId == documentation_id
        ]
        for id in to_delete:
            self.bpmn_diagrams.delete(id)
            
    # Database schema methods
    def get_database_schema(self, project_id: str) -> Optional[DatabaseSchemaInfo]:
        for schema in self.database_schemas.get_all():
            if schema.projectId == project_id:
                return schema
        return None
        
    def create_database_schema(self, data: dict) -> DatabaseSchemaInfo:
        return self.database_schemas.create(data)
        
    def delete_database_schema(self, project_id: str):
        to_delete = [
            s.id for s in self.database_schemas.get_all() 
            if s.projectId == project_id
        ]
        for id in to_delete:
            self.database_schemas.delete(id)


# Global storage instance
storage = StorageManager()
