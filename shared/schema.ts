import { z } from "zod";

// Project - represents an analyzed repository with generated artifacts
export const projectSchema = z.object({
  id: z.string(),
  name: z.string(),
  repoUrl: z.string(),
  description: z.string().optional(),
  techStack: z.array(z.string()),
  analyzedAt: z.string(),
  status: z.enum(["pending", "analyzing", "completed", "error"]),
});

export type Project = z.infer<typeof projectSchema>;

export const insertProjectSchema = projectSchema.omit({ id: true, analyzedAt: true });
export type InsertProject = z.infer<typeof insertProjectSchema>;

// Repository Analysis - structured analysis of a GitHub repository
export const repoAnalysisSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  summary: z.string(),
  architecture: z.string(),
  features: z.array(z.object({
    name: z.string(),
    description: z.string(),
    files: z.array(z.string()),
  })),
  techStack: z.object({
    languages: z.array(z.string()),
    frameworks: z.array(z.string()),
    databases: z.array(z.string()),
    tools: z.array(z.string()),
  }),
  testingFramework: z.string().optional(),
  codePatterns: z.array(z.string()),
  createdAt: z.string(),
});

export type RepoAnalysis = z.infer<typeof repoAnalysisSchema>;

// Documentation - generated technical documentation
export const documentationSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  title: z.string(),
  content: z.string(),
  sections: z.array(z.object({
    title: z.string(),
    content: z.string(),
  })),
  createdAt: z.string(),
});

export type Documentation = z.infer<typeof documentationSchema>;

// BPMN Diagram - user journey flowcharts for each feature
export const bpmnDiagramSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  documentationId: z.string(),
  diagrams: z.array(z.object({
    featureName: z.string(),
    description: z.string(),
    mermaidCode: z.string(),
  })),
  createdAt: z.string(),
});

export type BPMNDiagram = z.infer<typeof bpmnDiagramSchema>;

// Feature Request - input describing a new feature
export const featureRequestSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  title: z.string(),
  description: z.string(),
  inputType: z.enum(["text", "file", "audio"]),
  rawInput: z.string().optional(),
  createdAt: z.string(),
});

export type FeatureRequest = z.infer<typeof featureRequestSchema>;

export const insertFeatureRequestSchema = z.object({
  projectId: z.string(),
  title: z.string(),
  description: z.string(),
  inputType: z.enum(["text", "file", "audio"]),
  rawInput: z.string().optional(),
});

export type InsertFeatureRequest = z.infer<typeof insertFeatureRequestSchema>;

// BRD - Business Requirement Document
export const brdSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  featureRequestId: z.string(),
  title: z.string(),
  version: z.string(),
  status: z.enum(["draft", "review", "approved"]),
  sourceDocumentation: z.string().nullable().optional(),
  content: z.object({
    overview: z.string(),
    objectives: z.array(z.string()),
    scope: z.object({
      inScope: z.array(z.string()),
      outOfScope: z.array(z.string()),
    }),
    existingSystemContext: z.object({
      relevantComponents: z.array(z.string()),
      relevantAPIs: z.array(z.string()),
      dataModelsAffected: z.array(z.string()),
    }).nullable().optional(),
    functionalRequirements: z.array(z.object({
      id: z.string(),
      title: z.string(),
      description: z.string(),
      priority: z.enum(["high", "medium", "low"]),
      acceptanceCriteria: z.array(z.string()),
      relatedComponents: z.array(z.string()).optional(),
    })),
    nonFunctionalRequirements: z.array(z.object({
      id: z.string(),
      category: z.string(),
      description: z.string(),
    })),
    technicalConsiderations: z.array(z.string()),
    dependencies: z.array(z.string()),
    assumptions: z.array(z.string()),
    risks: z.array(z.object({
      description: z.string(),
      mitigation: z.string(),
    })),
  }),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type BRD = z.infer<typeof brdSchema>;

// Test Case - generated test cases
export const testCaseSchema = z.object({
  id: z.string(),
  brdId: z.string(),
  requirementId: z.string(),
  title: z.string(),
  description: z.string(),
  type: z.enum(["unit", "integration", "e2e", "acceptance"]),
  priority: z.enum(["critical", "high", "medium", "low"]),
  preconditions: z.array(z.string()),
  steps: z.array(z.object({
    step: z.number(),
    action: z.string(),
    expectedResult: z.string(),
  })),
  expectedOutcome: z.string(),
  codeSnippet: z.string().optional(),
  createdAt: z.string(),
});

export type TestCase = z.infer<typeof testCaseSchema>;

// Test Data - generated test data
export const testDataSchema = z.object({
  id: z.string(),
  testCaseId: z.string(),
  name: z.string(),
  description: z.string(),
  dataType: z.enum(["valid", "invalid", "edge", "boundary"]),
  data: z.record(z.unknown()),
  createdAt: z.string(),
});

export type TestData = z.infer<typeof testDataSchema>;

// User Story - JIRA-style user stories generated from BRD
export const userStorySchema = z.object({
  id: z.string(),
  brdId: z.string(),
  storyKey: z.string(),
  title: z.string(),
  description: z.string(),
  asA: z.string(),
  iWant: z.string(),
  soThat: z.string(),
  acceptanceCriteria: z.array(z.string()),
  priority: z.enum(["highest", "high", "medium", "low", "lowest"]),
  storyPoints: z.number().nullable().optional(),
  labels: z.array(z.string()),
  epic: z.string().nullable().optional(),
  relatedRequirementId: z.string().nullable().optional(),
  technicalNotes: z.string().nullable().optional(),
  dependencies: z.array(z.string()),
  jiraKey: z.string().nullable().optional(),
  parentJiraKey: z.string().nullable().optional(),
  createdAt: z.string(),
});

export type UserStory = z.infer<typeof userStorySchema>;

// Workflow State - tracks the current step in the workflow
export const workflowStateSchema = z.object({
  currentStep: z.enum(["analyze", "document", "requirements", "brd", "test-cases", "test-data"]),
  projectId: z.string().optional(),
  featureRequestId: z.string().optional(),
  brdId: z.string().optional(),
});

export type WorkflowState = z.infer<typeof workflowStateSchema>;

// Database Schema - external database schema information
export const databaseColumnSchema = z.object({
  name: z.string(),
  dataType: z.string(),
  isNullable: z.boolean(),
  defaultValue: z.string().nullable().optional(),
  isPrimaryKey: z.boolean().optional(),
  isForeignKey: z.boolean().optional(),
  references: z.string().nullable().optional(),
});

export type DatabaseColumn = z.infer<typeof databaseColumnSchema>;

export const databaseTableSchema = z.object({
  name: z.string(),
  columns: z.array(databaseColumnSchema),
  rowCount: z.number().optional(),
});

export type DatabaseTable = z.infer<typeof databaseTableSchema>;

export const databaseSchemaInfoSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  connectionString: z.string(),
  databaseName: z.string(),
  tables: z.array(databaseTableSchema),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type DatabaseSchemaInfo = z.infer<typeof databaseSchemaInfoSchema>;

// Knowledge Base Document - for RAG system
export const knowledgeDocumentSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  filename: z.string(),
  originalName: z.string(),
  contentType: z.string(),
  size: z.number(),
  chunkCount: z.number(),
  status: z.enum(["processing", "ready", "error"]),
  errorMessage: z.string().nullable().optional(),
  createdAt: z.string(),
});

export type KnowledgeDocument = z.infer<typeof knowledgeDocumentSchema>;

export const insertKnowledgeDocumentSchema = knowledgeDocumentSchema.omit({ 
  id: true, 
  createdAt: true,
  chunkCount: true,
  status: true,
  errorMessage: true 
});
export type InsertKnowledgeDocument = z.infer<typeof insertKnowledgeDocumentSchema>;

// Knowledge Chunk - for vector storage in MongoDB
export const knowledgeChunkSchema = z.object({
  documentId: z.string(),
  projectId: z.string(),
  content: z.string(),
  chunkIndex: z.number(),
  embedding: z.array(z.number()).optional(),
  metadata: z.object({
    filename: z.string(),
    pageNumber: z.number().optional(),
    section: z.string().optional(),
  }),
});

export type KnowledgeChunk = z.infer<typeof knowledgeChunkSchema>;

// User type for auth (keeping existing)
export const users = {
  id: "string",
  username: "string",
  password: "string",
};

export const insertUserSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = { id: string; username: string; password: string };
