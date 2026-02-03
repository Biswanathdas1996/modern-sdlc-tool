from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum

class ProjectStatus(str, Enum):
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    error = "error"

class RequestType(str, Enum):
    feature = "feature"
    bug = "bug"
    change_request = "change_request"

class InputType(str, Enum):
    text = "text"
    file = "file"
    audio = "audio"

class BRDStatus(str, Enum):
    draft = "draft"
    review = "review"
    approved = "approved"

class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"

class StoryPriority(str, Enum):
    highest = "highest"
    high = "high"
    medium = "medium"
    low = "low"
    lowest = "lowest"

class TestCaseCategory(str, Enum):
    happy_path = "happy_path"
    edge_case = "edge_case"
    negative = "negative"
    e2e = "e2e"

class TestCaseType(str, Enum):
    unit = "unit"
    integration = "integration"
    e2e = "e2e"
    acceptance = "acceptance"

class TestCasePriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"

class TestDataType(str, Enum):
    valid = "valid"
    invalid = "invalid"
    edge = "edge"
    boundary = "boundary"

class KnowledgeDocStatus(str, Enum):
    processing = "processing"
    ready = "ready"
    error = "error"

class Project(BaseModel):
    id: str
    name: str
    repoUrl: str
    description: Optional[str] = None
    techStack: List[str] = []
    analyzedAt: str
    status: ProjectStatus

class Feature(BaseModel):
    name: str
    description: str
    files: List[str] = []

class TechStack(BaseModel):
    languages: List[str] = []
    frameworks: List[str] = []
    databases: List[str] = []
    tools: List[str] = []

class RepoAnalysis(BaseModel):
    id: str
    projectId: str
    summary: str
    architecture: str
    features: List[Feature] = []
    techStack: TechStack
    testingFramework: Optional[str] = None
    codePatterns: List[str] = []
    createdAt: str

class Section(BaseModel):
    title: str
    content: str

class DatabaseColumn(BaseModel):
    name: str
    dataType: str
    isNullable: bool
    defaultValue: Optional[str] = None
    isPrimaryKey: Optional[bool] = None
    isForeignKey: Optional[bool] = None
    references: Optional[str] = None

class DatabaseTable(BaseModel):
    name: str
    columns: List[DatabaseColumn]
    rowCount: Optional[int] = None

class DatabaseSchemaEmbedded(BaseModel):
    databaseName: str
    connectionString: str
    tables: List[DatabaseTable]

class Documentation(BaseModel):
    id: str
    projectId: str
    title: str
    content: str
    sections: List[Section] = []
    databaseSchema: Optional[DatabaseSchemaEmbedded] = None
    createdAt: str

class BPMNDiagramItem(BaseModel):
    featureName: str
    description: str
    mermaidCode: str

class BPMNDiagram(BaseModel):
    id: str
    projectId: str
    documentationId: str
    diagrams: List[BPMNDiagramItem] = []
    createdAt: str

class FeatureRequest(BaseModel):
    id: str
    projectId: str
    title: str
    description: str
    inputType: InputType
    requestType: RequestType = RequestType.feature
    rawInput: Optional[str] = None
    createdAt: str

class KnowledgeSource(BaseModel):
    filename: str
    chunkPreview: str

class Scope(BaseModel):
    inScope: List[str] = []
    outOfScope: List[str] = []

class ExistingSystemContext(BaseModel):
    relevantComponents: List[str] = []
    relevantAPIs: List[str] = []
    dataModelsAffected: List[str] = []

class FunctionalRequirement(BaseModel):
    id: str
    title: str
    description: str
    priority: Priority
    acceptanceCriteria: List[str] = []
    relatedComponents: Optional[List[str]] = None

class NonFunctionalRequirement(BaseModel):
    id: str
    category: str
    description: str

class Risk(BaseModel):
    description: str
    mitigation: str

class BRDContent(BaseModel):
    overview: str
    objectives: List[str] = []
    scope: Scope
    existingSystemContext: Optional[ExistingSystemContext] = None
    functionalRequirements: List[FunctionalRequirement] = []
    nonFunctionalRequirements: List[NonFunctionalRequirement] = []
    technicalConsiderations: List[str] = []
    dependencies: List[str] = []
    assumptions: List[str] = []
    risks: List[Risk] = []

class BRD(BaseModel):
    id: str
    projectId: str
    featureRequestId: str
    requestType: RequestType = RequestType.feature
    title: str
    version: str
    status: BRDStatus
    sourceDocumentation: Optional[str] = None
    knowledgeSources: Optional[List[KnowledgeSource]] = None
    content: BRDContent
    createdAt: str
    updatedAt: str

class TestStep(BaseModel):
    step: int
    action: str
    expectedResult: str

class TestCase(BaseModel):
    id: str
    brdId: str
    requirementId: str
    title: str
    description: str
    category: TestCaseCategory
    type: TestCaseType
    priority: TestCasePriority
    preconditions: List[str] = []
    steps: List[TestStep] = []
    expectedOutcome: str
    codeSnippet: Optional[str] = None
    createdAt: str

class TestData(BaseModel):
    id: str
    testCaseId: str
    name: str
    description: str
    dataType: TestDataType
    data: Dict[str, Any] = {}
    createdAt: str

class UserStory(BaseModel):
    id: str
    brdId: str
    storyKey: str
    title: str
    description: str
    asA: str
    iWant: str
    soThat: str
    acceptanceCriteria: List[str] = []
    priority: StoryPriority
    storyPoints: Optional[int] = None
    labels: List[str] = []
    epic: Optional[str] = None
    relatedRequirementId: Optional[str] = None
    technicalNotes: Optional[str] = None
    dependencies: List[str] = []
    jiraKey: Optional[str] = None
    parentJiraKey: Optional[str] = None
    createdAt: str

class DatabaseSchemaInfo(BaseModel):
    id: str
    projectId: str
    connectionString: str
    databaseName: str
    tables: List[DatabaseTable]
    createdAt: str
    updatedAt: str

class KnowledgeDocument(BaseModel):
    id: str
    projectId: str
    filename: str
    originalName: str
    contentType: str
    size: int
    chunkCount: int
    status: KnowledgeDocStatus
    errorMessage: Optional[str] = None
    createdAt: str

class AnalyzeRequest(BaseModel):
    repoUrl: str

class RequirementsRequest(BaseModel):
    title: str
    description: Optional[str] = None
    inputType: InputType
    requestType: RequestType = RequestType.feature
