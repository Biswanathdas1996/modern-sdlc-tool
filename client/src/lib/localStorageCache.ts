export type SessionArtifact = "project" | "documentation" | "analysis" | "featureRequest" | "brd" | "userStories" | "testCases" | "testData" | "bpmn" | "databaseSchema" | "copilotPrompt";

export interface WorkflowSession {
  sessionId: string;
  createdAt: number;
  projectName?: string;
  requestType?: string;
  featureTitle?: string;
}
