"""Pydantic schemas for domain entities."""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from schemas.requests import (
    ProjectStatus, RequestType, InputType, Priority, 
    BRDStatus
)
from enum import Enum


class StoryPriority(str, Enum):
    """User story priority."""
    highest = "highest"
    high = "high"
    medium = "medium"
    low = "low"
    lowest = "lowest"


class TestCaseCategory(str, Enum):
    """Test case category."""
    happy_path = "happy_path"
    edge_case = "edge_case"
    negative = "negative"
    e2e = "e2e"


class TestCaseType(str, Enum):
    """Test case type."""
    unit = "unit"
    integration = "integration"
    e2e = "e2e"
    acceptance = "acceptance"


class TestCasePriority(str, Enum):
    """Test case priority."""
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TestDataType(str, Enum):
    """Test data type."""
    valid = "valid"
    invalid = "invalid"
    edge = "edge"
    boundary = "boundary"


class KnowledgeDocStatus(str, Enum):
    """Knowledge document status."""
    processing = "processing"
    ready = "ready"
    error = "error"


# Domain entity schemas
class Feature(BaseModel):
    """Feature identified in codebase."""
    name: str
    description: str
    files: List[str] = []


class TechStack(BaseModel):
    """Technology stack information."""
    languages: List[str] = []
    frameworks: List[str] = []
    databases: List[str] = []
    tools: List[str] = []


class Section(BaseModel):
    """Documentation section."""
    title: str
    content: str


class DatabaseColumn(BaseModel):
    """Database column information."""
    name: str
    dataType: str
    isNullable: bool
    defaultValue: Optional[str] = None
    isPrimaryKey: Optional[bool] = None
    isForeignKey: Optional[bool] = None
    references: Optional[str] = None


class DatabaseTable(BaseModel):
    """Database table information."""
    name: str
    columns: List[DatabaseColumn]
    rowCount: Optional[int] = None


class DatabaseSchemaEmbedded(BaseModel):
    """Embedded database schema."""
    databaseName: str
    connectionString: str
    tables: List[DatabaseTable]


class KnowledgeSource(BaseModel):
    """Knowledge source reference."""
    filename: str
    chunkPreview: str


class Scope(BaseModel):
    """BRD scope definition."""
    inScope: List[str] = []
    outOfScope: List[str] = []


class ExistingSystemContext(BaseModel):
    """Existing system context."""
    relevantComponents: List[str] = []
    relevantAPIs: List[str] = []
    dataModelsAffected: List[str] = []


class FunctionalRequirement(BaseModel):
    """Functional requirement."""
    id: str
    title: str
    description: str
    priority: Priority
    acceptanceCriteria: List[str] = []
    relatedComponents: Optional[List[str]] = None


class NonFunctionalRequirement(BaseModel):
    """Non-functional requirement."""
    id: str
    category: str
    description: str


class Risk(BaseModel):
    """Risk and mitigation."""
    description: str
    mitigation: str


class BRDContent(BaseModel):
    """BRD content structure."""
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


class TestStep(BaseModel):
    """Test case step."""
    step: int
    action: str
    expectedResult: str


class BPMNDiagramItem(BaseModel):
    """BPMN diagram item."""
    featureName: str
    description: str
    mermaidCode: str


# Full entity models
class Project(BaseModel):
    """Project entity."""
    id: str
    name: str
    repoUrl: str
    description: Optional[str] = None
    techStack: List[str] = []
    analyzedAt: str
    status: ProjectStatus


class RepoAnalysis(BaseModel):
    """Repository analysis entity."""
    id: str
    projectId: str
    summary: str
    architecture: str
    features: List[Feature] = []
    techStack: TechStack
    testingFramework: Optional[str] = None
    codePatterns: List[str] = []
    createdAt: str


class Documentation(BaseModel):
    """Documentation entity."""
    id: str
    projectId: str
    title: str
    content: str
    sections: List[Section] = []
    databaseSchema: Optional[DatabaseSchemaEmbedded] = None
    createdAt: str


class BPMNDiagram(BaseModel):
    """BPMN diagram entity."""
    id: str
    projectId: str
    documentationId: str
    diagrams: List[BPMNDiagramItem] = []
    createdAt: str


class FeatureRequest(BaseModel):
    """Feature request entity."""
    id: str
    projectId: str
    title: str
    description: str
    inputType: InputType
    requestType: RequestType = RequestType.feature
    rawInput: Optional[str] = None
    createdAt: str


class BRD(BaseModel):
    """Business Requirements Document entity."""
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


class TestCase(BaseModel):
    """Test case entity."""
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
    """Test data entity."""
    id: str
    testCaseId: str
    name: str
    description: str
    dataType: TestDataType
    data: Dict[str, Any] = {}
    createdAt: str


class UserStory(BaseModel):
    """User story entity."""
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
    """Database schema information entity."""
    id: str
    projectId: str
    connectionString: str
    databaseName: str
    tables: List[DatabaseTable]
    createdAt: str
    updatedAt: str


class KnowledgeDocument(BaseModel):
    """Knowledge document entity."""
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
