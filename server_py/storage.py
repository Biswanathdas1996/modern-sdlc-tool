from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
from models import (
    Project, RepoAnalysis, Documentation, FeatureRequest, BRD,
    TestCase, TestData, UserStory, BPMNDiagram, DatabaseSchemaInfo, KnowledgeDocument
)

class MemStorage:
    def __init__(self):
        self.projects: Dict[str, Project] = {}
        self.analyses: Dict[str, RepoAnalysis] = {}
        self.documentation: Dict[str, Documentation] = {}
        self.feature_requests: Dict[str, FeatureRequest] = {}
        self.brds: Dict[str, BRD] = {}
        self.test_cases: Dict[str, TestCase] = {}
        self.test_data: Dict[str, TestData] = {}
        self.user_stories: Dict[str, UserStory] = {}
        self.bpmn_diagrams: Dict[str, BPMNDiagram] = {}
        self.database_schemas: Dict[str, DatabaseSchemaInfo] = {}
        self.knowledge_documents: Dict[str, KnowledgeDocument] = {}
        
        self.current_project_id: Optional[str] = None
        self.current_feature_request_id: Optional[str] = None
        self.current_brd_id: Optional[str] = None

    def get_project(self, id: str) -> Optional[Project]:
        return self.projects.get(id)

    def get_all_projects(self) -> List[Project]:
        projects = list(self.projects.values())
        return sorted(projects, key=lambda p: p.analyzedAt, reverse=True)

    def create_project(self, data: dict) -> Project:
        id = str(uuid.uuid4())
        project = Project(
            id=id,
            name=data["name"],
            repoUrl=data["repoUrl"],
            description=data.get("description"),
            techStack=data.get("techStack", []),
            analyzedAt=datetime.utcnow().isoformat(),
            status=data.get("status", "pending")
        )
        self.projects[id] = project
        self.current_project_id = id
        return project

    def update_project(self, id: str, updates: dict) -> Optional[Project]:
        project = self.projects.get(id)
        if not project:
            return None
        project_dict = project.model_dump()
        project_dict.update(updates)
        updated = Project(**project_dict)
        self.projects[id] = updated
        return updated

    def delete_project(self, id: str) -> None:
        self.projects.pop(id, None)

    def get_analysis(self, project_id: str) -> Optional[RepoAnalysis]:
        for analysis in self.analyses.values():
            if analysis.projectId == project_id:
                return analysis
        return None

    def create_analysis(self, data: dict) -> RepoAnalysis:
        id = str(uuid.uuid4())
        analysis = RepoAnalysis(
            id=id,
            projectId=data["projectId"],
            summary=data.get("summary", ""),
            architecture=data.get("architecture", ""),
            features=data.get("features", []),
            techStack=data.get("techStack", {}),
            testingFramework=data.get("testingFramework"),
            codePatterns=data.get("codePatterns", []),
            createdAt=datetime.utcnow().isoformat()
        )
        self.analyses[id] = analysis
        return analysis

    def get_documentation(self, project_id: str) -> Optional[Documentation]:
        for doc in self.documentation.values():
            if doc.projectId == project_id:
                return doc
        return None

    def create_documentation(self, data: dict) -> Documentation:
        id = str(uuid.uuid4())
        doc = Documentation(
            id=id,
            projectId=data["projectId"],
            title=data.get("title", ""),
            content=data.get("content", ""),
            sections=data.get("sections", []),
            databaseSchema=data.get("databaseSchema"),
            createdAt=datetime.utcnow().isoformat()
        )
        self.documentation[id] = doc
        return doc

    def update_documentation(self, project_id: str, updates: dict) -> Optional[Documentation]:
        existing = self.get_documentation(project_id)
        if not existing:
            return None
        doc_dict = existing.model_dump()
        doc_dict.update(updates)
        updated = Documentation(**doc_dict)
        self.documentation[existing.id] = updated
        return updated

    def get_feature_request(self, id: str) -> Optional[FeatureRequest]:
        return self.feature_requests.get(id)

    def get_feature_requests_by_project(self, project_id: str) -> List[FeatureRequest]:
        return [r for r in self.feature_requests.values() if r.projectId == project_id]

    def create_feature_request(self, data: dict) -> FeatureRequest:
        id = str(uuid.uuid4())
        request = FeatureRequest(
            id=id,
            projectId=data["projectId"],
            title=data["title"],
            description=data.get("description", ""),
            inputType=data.get("inputType", "text"),
            requestType=data.get("requestType", "feature"),
            rawInput=data.get("rawInput"),
            createdAt=datetime.utcnow().isoformat()
        )
        self.feature_requests[id] = request
        self.current_feature_request_id = id
        return request

    def get_current_feature_request(self) -> Optional[FeatureRequest]:
        if not self.current_feature_request_id:
            return None
        return self.feature_requests.get(self.current_feature_request_id)

    def set_current_feature_request(self, id: str) -> None:
        self.current_feature_request_id = id

    def get_brd(self, id: str) -> Optional[BRD]:
        return self.brds.get(id)

    def get_brd_by_project(self, project_id: str) -> Optional[BRD]:
        for brd in self.brds.values():
            if brd.projectId == project_id:
                return brd
        return None

    def create_brd(self, data: dict) -> BRD:
        id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        brd = BRD(
            id=id,
            projectId=data.get("projectId", "global"),
            featureRequestId=data.get("featureRequestId", ""),
            requestType=data.get("requestType", "feature"),
            title=data.get("title", ""),
            version=data.get("version", "1.0"),
            status=data.get("status", "draft"),
            sourceDocumentation=data.get("sourceDocumentation"),
            knowledgeSources=data.get("knowledgeSources"),
            content=data.get("content", {}),
            createdAt=now,
            updatedAt=now
        )
        self.brds[id] = brd
        self.current_brd_id = id
        return brd

    def update_brd(self, id: str, updates: dict) -> Optional[BRD]:
        brd = self.brds.get(id)
        if not brd:
            return None
        brd_dict = brd.model_dump()
        brd_dict.update(updates)
        brd_dict["updatedAt"] = datetime.utcnow().isoformat()
        updated = BRD(**brd_dict)
        self.brds[id] = updated
        return updated

    def get_current_brd(self) -> Optional[BRD]:
        if not self.current_brd_id:
            return None
        return self.brds.get(self.current_brd_id)

    def get_test_cases(self, brd_id: str) -> List[TestCase]:
        return [tc for tc in self.test_cases.values() if tc.brdId == brd_id]

    def create_test_case(self, data: dict) -> TestCase:
        id = str(uuid.uuid4())
        tc = TestCase(
            id=id,
            brdId=data["brdId"],
            requirementId=data.get("requirementId", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            category=data.get("category", "happy_path"),
            type=data.get("type", "unit"),
            priority=data.get("priority", "medium"),
            preconditions=data.get("preconditions", []),
            steps=data.get("steps", []),
            expectedOutcome=data.get("expectedOutcome", ""),
            codeSnippet=data.get("codeSnippet"),
            createdAt=datetime.utcnow().isoformat()
        )
        self.test_cases[id] = tc
        return tc

    def create_test_cases(self, test_cases: List[dict]) -> List[TestCase]:
        return [self.create_test_case(tc) for tc in test_cases]

    def get_test_data(self, test_case_id: str) -> List[TestData]:
        return [td for td in self.test_data.values() if td.testCaseId == test_case_id]

    def get_all_test_data(self) -> List[TestData]:
        return list(self.test_data.values())

    def create_test_data(self, data: dict) -> TestData:
        id = str(uuid.uuid4())
        valid_types = {"valid", "invalid", "edge", "boundary"}
        raw_type = str(data.get("dataType", "valid")).lower().strip()
        data_type = raw_type if raw_type in valid_types else "valid"
        td = TestData(
            id=id,
            testCaseId=data["testCaseId"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            dataType=data_type,
            data=data.get("data", {}),
            createdAt=datetime.utcnow().isoformat()
        )
        self.test_data[id] = td
        return td

    def create_test_data_batch(self, data_list: List[dict]) -> List[TestData]:
        return [self.create_test_data(d) for d in data_list]

    def get_user_stories(self, brd_id: str) -> List[UserStory]:
        return [s for s in self.user_stories.values() if s.brdId == brd_id]

    def create_user_story(self, data: dict) -> UserStory:
        id = str(uuid.uuid4())
        story = UserStory(
            id=id,
            brdId=data["brdId"],
            storyKey=data.get("storyKey", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            asA=data.get("asA", ""),
            iWant=data.get("iWant", ""),
            soThat=data.get("soThat", ""),
            acceptanceCriteria=data.get("acceptanceCriteria", []),
            priority=data.get("priority", "medium"),
            storyPoints=data.get("storyPoints"),
            labels=data.get("labels", []),
            epic=data.get("epic"),
            relatedRequirementId=data.get("relatedRequirementId"),
            technicalNotes=data.get("technicalNotes"),
            dependencies=data.get("dependencies", []),
            jiraKey=data.get("jiraKey"),
            parentJiraKey=data.get("parentJiraKey"),
            createdAt=datetime.utcnow().isoformat()
        )
        self.user_stories[id] = story
        return story

    def create_user_stories(self, stories: List[dict]) -> List[UserStory]:
        return [self.create_user_story(s) for s in stories]

    def update_user_story(self, id: str, updates: dict) -> Optional[UserStory]:
        story = self.user_stories.get(id)
        if not story:
            return None
        story_dict = story.model_dump()
        story_dict.update(updates)
        updated = UserStory(**story_dict)
        self.user_stories[id] = updated
        return updated

    def delete_user_story(self, id: str) -> bool:
        if id in self.user_stories:
            del self.user_stories[id]
            return True
        return False

    def get_bpmn_diagram(self, documentation_id: str) -> Optional[BPMNDiagram]:
        for diagram in self.bpmn_diagrams.values():
            if diagram.documentationId == documentation_id:
                return diagram
        return None

    def create_bpmn_diagram(self, data: dict) -> BPMNDiagram:
        id = str(uuid.uuid4())
        diagram = BPMNDiagram(
            id=id,
            projectId=data.get("projectId", ""),
            documentationId=data.get("documentationId", ""),
            diagrams=data.get("diagrams", []),
            createdAt=datetime.utcnow().isoformat()
        )
        self.bpmn_diagrams[id] = diagram
        return diagram

    def delete_bpmn_diagram(self, documentation_id: str) -> None:
        to_delete = [id for id, d in self.bpmn_diagrams.items() if d.documentationId == documentation_id]
        for id in to_delete:
            del self.bpmn_diagrams[id]

    def get_database_schema(self, project_id: str) -> Optional[DatabaseSchemaInfo]:
        for schema in self.database_schemas.values():
            if schema.projectId == project_id:
                return schema
        return None

    def create_database_schema(self, data: dict) -> DatabaseSchemaInfo:
        id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        schema = DatabaseSchemaInfo(
            id=id,
            projectId=data["projectId"],
            connectionString=data.get("connectionString", ""),
            databaseName=data.get("databaseName", ""),
            tables=data.get("tables", []),
            createdAt=now,
            updatedAt=now
        )
        self.database_schemas[id] = schema
        return schema

    def update_database_schema(self, project_id: str, updates: dict) -> Optional[DatabaseSchemaInfo]:
        existing = self.get_database_schema(project_id)
        if not existing:
            return None
        schema_dict = existing.model_dump()
        schema_dict.update(updates)
        schema_dict["updatedAt"] = datetime.utcnow().isoformat()
        updated = DatabaseSchemaInfo(**schema_dict)
        self.database_schemas[existing.id] = updated
        return updated

    def delete_database_schema(self, project_id: str) -> None:
        to_delete = [id for id, s in self.database_schemas.items() if s.projectId == project_id]
        for id in to_delete:
            del self.database_schemas[id]

    def get_knowledge_documents(self, project_id: str) -> List[KnowledgeDocument]:
        docs = [d for d in self.knowledge_documents.values() if d.projectId == project_id]
        return sorted(docs, key=lambda d: d.createdAt, reverse=True)

    def get_knowledge_document(self, id: str) -> Optional[KnowledgeDocument]:
        return self.knowledge_documents.get(id)

    def create_knowledge_document(self, data: dict) -> KnowledgeDocument:
        id = str(uuid.uuid4())
        doc = KnowledgeDocument(
            id=id,
            projectId=data["projectId"],
            filename=data.get("filename", ""),
            originalName=data.get("originalName", ""),
            contentType=data.get("contentType", ""),
            size=data.get("size", 0),
            chunkCount=0,
            status="processing",
            errorMessage=None,
            createdAt=datetime.utcnow().isoformat()
        )
        self.knowledge_documents[id] = doc
        return doc

    def update_knowledge_document(self, id: str, updates: dict) -> Optional[KnowledgeDocument]:
        doc = self.knowledge_documents.get(id)
        if not doc:
            return None
        doc_dict = doc.model_dump()
        doc_dict.update(updates)
        updated = KnowledgeDocument(**doc_dict)
        self.knowledge_documents[id] = updated
        return updated

    def delete_knowledge_document(self, id: str) -> bool:
        if id in self.knowledge_documents:
            del self.knowledge_documents[id]
            return True
        return False


storage = MemStorage()
