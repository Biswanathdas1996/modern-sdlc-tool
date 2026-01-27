import { randomUUID } from "crypto";
import type { 
  Project, 
  RepoAnalysis, 
  Documentation, 
  FeatureRequest, 
  BRD, 
  TestCase, 
  TestData,
  UserStory,
  BPMNDiagram
} from "@shared/schema";

export interface IStorage {
  // Projects
  getProject(id: string): Promise<Project | undefined>;
  getAllProjects(): Promise<Project[]>;
  createProject(project: Omit<Project, "id" | "analyzedAt">): Promise<Project>;
  updateProject(id: string, updates: Partial<Project>): Promise<Project | undefined>;
  deleteProject(id: string): Promise<void>;
  
  // Repository Analysis
  getAnalysis(projectId: string): Promise<RepoAnalysis | undefined>;
  createAnalysis(analysis: Omit<RepoAnalysis, "id" | "createdAt">): Promise<RepoAnalysis>;
  
  // Documentation
  getDocumentation(projectId: string): Promise<Documentation | undefined>;
  createDocumentation(doc: Omit<Documentation, "id" | "createdAt">): Promise<Documentation>;
  
  // Feature Requests
  getFeatureRequest(id: string): Promise<FeatureRequest | undefined>;
  getFeatureRequestsByProject(projectId: string): Promise<FeatureRequest[]>;
  createFeatureRequest(request: Omit<FeatureRequest, "id" | "createdAt">): Promise<FeatureRequest>;
  getCurrentFeatureRequest(): Promise<FeatureRequest | undefined>;
  setCurrentFeatureRequest(id: string): Promise<void>;
  
  // BRDs
  getBRD(id: string): Promise<BRD | undefined>;
  getBRDByProject(projectId: string): Promise<BRD | undefined>;
  createBRD(brd: Omit<BRD, "id" | "createdAt" | "updatedAt">): Promise<BRD>;
  updateBRD(id: string, updates: Partial<BRD>): Promise<BRD | undefined>;
  getCurrentBRD(): Promise<BRD | undefined>;
  
  // Test Cases
  getTestCases(brdId: string): Promise<TestCase[]>;
  createTestCase(testCase: Omit<TestCase, "id" | "createdAt">): Promise<TestCase>;
  createTestCases(testCases: Omit<TestCase, "id" | "createdAt">[]): Promise<TestCase[]>;
  
  // Test Data
  getTestData(testCaseId: string): Promise<TestData[]>;
  getAllTestData(): Promise<TestData[]>;
  createTestData(data: Omit<TestData, "id" | "createdAt">): Promise<TestData>;
  createTestDataBatch(data: Omit<TestData, "id" | "createdAt">[]): Promise<TestData[]>;
  
  // User Stories
  getUserStories(brdId: string): Promise<UserStory[]>;
  createUserStory(story: Omit<UserStory, "id" | "createdAt">): Promise<UserStory>;
  createUserStories(stories: Omit<UserStory, "id" | "createdAt">[]): Promise<UserStory[]>;
  updateUserStory(id: string, updates: Partial<UserStory>): Promise<UserStory | undefined>;
  deleteUserStory(id: string): Promise<boolean>;
  
  // BPMN Diagrams
  getBPMNDiagram(documentationId: string): Promise<BPMNDiagram | undefined>;
  createBPMNDiagram(diagram: Omit<BPMNDiagram, "id" | "createdAt">): Promise<BPMNDiagram>;
  deleteBPMNDiagram(documentationId: string): Promise<void>;
}

export class MemStorage implements IStorage {
  private projects: Map<string, Project> = new Map();
  private analyses: Map<string, RepoAnalysis> = new Map();
  private documentation: Map<string, Documentation> = new Map();
  private featureRequests: Map<string, FeatureRequest> = new Map();
  private brds: Map<string, BRD> = new Map();
  private testCases: Map<string, TestCase> = new Map();
  private testData: Map<string, TestData> = new Map();
  private userStories: Map<string, UserStory> = new Map();
  private bpmnDiagrams: Map<string, BPMNDiagram> = new Map();
  
  private currentProjectId: string | null = null;
  private currentFeatureRequestId: string | null = null;
  private currentBRDId: string | null = null;

  // Projects
  async getProject(id: string): Promise<Project | undefined> {
    return this.projects.get(id);
  }

  async getAllProjects(): Promise<Project[]> {
    return Array.from(this.projects.values()).sort(
      (a, b) => new Date(b.analyzedAt).getTime() - new Date(a.analyzedAt).getTime()
    );
  }

  async createProject(project: Omit<Project, "id" | "analyzedAt">): Promise<Project> {
    const id = randomUUID();
    const newProject: Project = {
      ...project,
      id,
      analyzedAt: new Date().toISOString(),
    };
    this.projects.set(id, newProject);
    this.currentProjectId = id;
    return newProject;
  }

  async updateProject(id: string, updates: Partial<Project>): Promise<Project | undefined> {
    const project = this.projects.get(id);
    if (!project) return undefined;
    const updated = { ...project, ...updates };
    this.projects.set(id, updated);
    return updated;
  }

  async deleteProject(id: string): Promise<void> {
    this.projects.delete(id);
  }

  // Repository Analysis
  async getAnalysis(projectId: string): Promise<RepoAnalysis | undefined> {
    return Array.from(this.analyses.values()).find((a) => a.projectId === projectId);
  }

  async createAnalysis(analysis: Omit<RepoAnalysis, "id" | "createdAt">): Promise<RepoAnalysis> {
    const id = randomUUID();
    const newAnalysis: RepoAnalysis = {
      ...analysis,
      id,
      createdAt: new Date().toISOString(),
    };
    this.analyses.set(id, newAnalysis);
    return newAnalysis;
  }

  // Documentation
  async getDocumentation(projectId: string): Promise<Documentation | undefined> {
    return Array.from(this.documentation.values()).find((d) => d.projectId === projectId);
  }

  async createDocumentation(doc: Omit<Documentation, "id" | "createdAt">): Promise<Documentation> {
    const id = randomUUID();
    const newDoc: Documentation = {
      ...doc,
      id,
      createdAt: new Date().toISOString(),
    };
    this.documentation.set(id, newDoc);
    return newDoc;
  }

  // Feature Requests
  async getFeatureRequest(id: string): Promise<FeatureRequest | undefined> {
    return this.featureRequests.get(id);
  }

  async getFeatureRequestsByProject(projectId: string): Promise<FeatureRequest[]> {
    return Array.from(this.featureRequests.values()).filter((r) => r.projectId === projectId);
  }

  async createFeatureRequest(request: Omit<FeatureRequest, "id" | "createdAt">): Promise<FeatureRequest> {
    const id = randomUUID();
    const newRequest: FeatureRequest = {
      ...request,
      id,
      createdAt: new Date().toISOString(),
    };
    this.featureRequests.set(id, newRequest);
    this.currentFeatureRequestId = id;
    return newRequest;
  }

  async getCurrentFeatureRequest(): Promise<FeatureRequest | undefined> {
    if (!this.currentFeatureRequestId) return undefined;
    return this.featureRequests.get(this.currentFeatureRequestId);
  }

  async setCurrentFeatureRequest(id: string): Promise<void> {
    this.currentFeatureRequestId = id;
  }

  // BRDs
  async getBRD(id: string): Promise<BRD | undefined> {
    return this.brds.get(id);
  }

  async getBRDByProject(projectId: string): Promise<BRD | undefined> {
    return Array.from(this.brds.values()).find((b) => b.projectId === projectId);
  }

  async createBRD(brd: Omit<BRD, "id" | "createdAt" | "updatedAt">): Promise<BRD> {
    const id = randomUUID();
    const now = new Date().toISOString();
    const newBRD: BRD = {
      ...brd,
      id,
      createdAt: now,
      updatedAt: now,
    };
    this.brds.set(id, newBRD);
    this.currentBRDId = id;
    return newBRD;
  }

  async updateBRD(id: string, updates: Partial<BRD>): Promise<BRD | undefined> {
    const brd = this.brds.get(id);
    if (!brd) return undefined;
    const updated = { ...brd, ...updates, updatedAt: new Date().toISOString() };
    this.brds.set(id, updated);
    return updated;
  }

  async getCurrentBRD(): Promise<BRD | undefined> {
    if (!this.currentBRDId) return undefined;
    return this.brds.get(this.currentBRDId);
  }

  // Test Cases
  async getTestCases(brdId: string): Promise<TestCase[]> {
    return Array.from(this.testCases.values()).filter((t) => t.brdId === brdId);
  }

  async createTestCase(testCase: Omit<TestCase, "id" | "createdAt">): Promise<TestCase> {
    const id = randomUUID();
    const newTestCase: TestCase = {
      ...testCase,
      id,
      createdAt: new Date().toISOString(),
    };
    this.testCases.set(id, newTestCase);
    return newTestCase;
  }

  async createTestCases(testCases: Omit<TestCase, "id" | "createdAt">[]): Promise<TestCase[]> {
    return Promise.all(testCases.map((tc) => this.createTestCase(tc)));
  }

  // Test Data
  async getTestData(testCaseId: string): Promise<TestData[]> {
    return Array.from(this.testData.values()).filter((d) => d.testCaseId === testCaseId);
  }

  async getAllTestData(): Promise<TestData[]> {
    return Array.from(this.testData.values());
  }

  async createTestData(data: Omit<TestData, "id" | "createdAt">): Promise<TestData> {
    const id = randomUUID();
    const newData: TestData = {
      ...data,
      id,
      createdAt: new Date().toISOString(),
    };
    this.testData.set(id, newData);
    return newData;
  }

  async createTestDataBatch(data: Omit<TestData, "id" | "createdAt">[]): Promise<TestData[]> {
    return Promise.all(data.map((d) => this.createTestData(d)));
  }

  // User Stories
  async getUserStories(brdId: string): Promise<UserStory[]> {
    return Array.from(this.userStories.values()).filter((s) => s.brdId === brdId);
  }

  async createUserStory(story: Omit<UserStory, "id" | "createdAt">): Promise<UserStory> {
    const id = randomUUID();
    const newStory: UserStory = {
      ...story,
      id,
      createdAt: new Date().toISOString(),
    };
    this.userStories.set(id, newStory);
    return newStory;
  }

  async createUserStories(stories: Omit<UserStory, "id" | "createdAt">[]): Promise<UserStory[]> {
    return Promise.all(stories.map((s) => this.createUserStory(s)));
  }

  async updateUserStory(id: string, updates: Partial<UserStory>): Promise<UserStory | undefined> {
    const story = this.userStories.get(id);
    if (!story) return undefined;
    const updatedStory = { ...story, ...updates, id: story.id, createdAt: story.createdAt };
    this.userStories.set(id, updatedStory);
    return updatedStory;
  }

  async deleteUserStory(id: string): Promise<boolean> {
    return this.userStories.delete(id);
  }

  async getBPMNDiagram(documentationId: string): Promise<BPMNDiagram | undefined> {
    return Array.from(this.bpmnDiagrams.values()).find(d => d.documentationId === documentationId);
  }

  async createBPMNDiagram(diagram: Omit<BPMNDiagram, "id" | "createdAt">): Promise<BPMNDiagram> {
    const id = randomUUID();
    const newDiagram: BPMNDiagram = {
      ...diagram,
      id,
      createdAt: new Date().toISOString(),
    };
    this.bpmnDiagrams.set(id, newDiagram);
    return newDiagram;
  }

  async deleteBPMNDiagram(documentationId: string): Promise<void> {
    const entries = Array.from(this.bpmnDiagrams.entries());
    for (const [id, diagram] of entries) {
      if (diagram.documentationId === documentationId) {
        this.bpmnDiagrams.delete(id);
      }
    }
  }
}

export const storage = new MemStorage();
