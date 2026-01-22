import OpenAI from "openai";
import type { RepoAnalysis, FeatureRequest, BRD, TestCase, TestData, Documentation, Project } from "@shared/schema";

const openai = new OpenAI({
  apiKey: process.env.AI_INTEGRATIONS_OPENAI_API_KEY,
  baseURL: process.env.AI_INTEGRATIONS_OPENAI_BASE_URL,
});

// Fetch repository contents from GitHub
async function fetchRepoContents(repoUrl: string): Promise<string> {
  const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!match) throw new Error("Invalid GitHub URL");
  
  const owner = match[1];
  const repo = match[2].replace(/\.git$/, "");
  
  try {
    // Fetch repository info
    const repoResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}`);
    if (!repoResponse.ok) throw new Error("Failed to fetch repository");
    const repoData = await repoResponse.json();
    
    // Fetch file tree
    const treeResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/trees/main?recursive=1`);
    let treeData: any = { tree: [] };
    if (treeResponse.ok) {
      treeData = await treeResponse.json();
    } else {
      // Try master branch
      const masterResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/trees/master?recursive=1`);
      if (masterResponse.ok) {
        treeData = await masterResponse.json();
      }
    }
    
    // Get key files content
    const keyFiles = ["package.json", "README.md", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml"];
    const fileContents: string[] = [];
    
    for (const file of keyFiles) {
      try {
        const contentResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${file}`);
        if (contentResponse.ok) {
          const contentData = await contentResponse.json();
          if (contentData.content) {
            const decoded = Buffer.from(contentData.content, "base64").toString("utf-8");
            fileContents.push(`--- ${file} ---\n${decoded}\n`);
          }
        }
      } catch {
        // File doesn't exist, skip
      }
    }
    
    // Build context
    const files = treeData.tree
      ?.filter((f: any) => f.type === "blob")
      .map((f: any) => f.path)
      .slice(0, 100) || [];
    
    return `
Repository: ${repoData.full_name}
Description: ${repoData.description || "No description"}
Language: ${repoData.language || "Unknown"}
Stars: ${repoData.stargazers_count}
Topics: ${repoData.topics?.join(", ") || "None"}

Files in repository:
${files.join("\n")}

Key file contents:
${fileContents.join("\n")}
    `.trim();
  } catch (error) {
    console.error("Error fetching repo contents:", error);
    return `Repository: ${owner}/${repo}\nNote: Limited access - could not fetch detailed contents.`;
  }
}

export async function analyzeRepository(repoUrl: string, projectId: string): Promise<RepoAnalysis> {
  const repoContext = await fetchRepoContents(repoUrl);
  
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `You are a senior software architect analyzing GitHub repositories. Analyze the provided repository information and generate comprehensive documentation about its structure, features, and technology stack.

Return your analysis as a JSON object with this exact structure:
{
  "summary": "Brief overview of what this repository does",
  "architecture": "Description of the architectural patterns and structure",
  "features": [
    {
      "name": "Feature name",
      "description": "What this feature does",
      "files": ["list", "of", "relevant", "files"]
    }
  ],
  "techStack": {
    "languages": ["list of programming languages"],
    "frameworks": ["list of frameworks"],
    "databases": ["list of databases if any"],
    "tools": ["list of tools like Docker, CI/CD, etc"]
  },
  "testingFramework": "Testing framework used if any",
  "codePatterns": ["list of design patterns or coding patterns observed"]
}`
      },
      {
        role: "user",
        content: `Analyze this repository:\n\n${repoContext}`
      }
    ],
    response_format: { type: "json_object" },
    max_completion_tokens: 4096,
  });
  
  const content = response.choices[0]?.message?.content || "{}";
  const analysisData = JSON.parse(content);
  
  return {
    ...analysisData,
    projectId,
    id: "",
    createdAt: "",
  } as RepoAnalysis;
}

export async function generateDocumentation(
  analysis: RepoAnalysis,
  project: Project
): Promise<Omit<Documentation, "id" | "createdAt">> {
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `You are a technical writer creating comprehensive documentation for a software project. Based on the repository analysis provided, generate detailed technical documentation.

Return a JSON object with this structure:
{
  "title": "Project Documentation Title",
  "content": "Full markdown content of the documentation",
  "sections": [
    {
      "title": "Section title",
      "content": "Section content in markdown"
    }
  ]
}`
      },
      {
        role: "user",
        content: `Generate documentation for this project:

Project Name: ${project.name}
Repository URL: ${project.repoUrl}

Analysis:
- Summary: ${analysis.summary}
- Architecture: ${analysis.architecture}
- Tech Stack: ${JSON.stringify(analysis.techStack)}
- Features: ${JSON.stringify(analysis.features)}
- Code Patterns: ${analysis.codePatterns?.join(", ")}
- Testing Framework: ${analysis.testingFramework || "Not specified"}`
      }
    ],
    response_format: { type: "json_object" },
    max_completion_tokens: 4096,
  });

  const rawContent = response.choices[0]?.message?.content || "{}";
  
  // Robust JSON parsing with fallback
  let docData: any;
  try {
    docData = JSON.parse(rawContent);
  } catch (parseError) {
    console.error("Failed to parse documentation JSON, attempting recovery:", parseError);
    const jsonMatch = rawContent.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        docData = JSON.parse(jsonMatch[0]);
      } catch {
        // Fallback to basic documentation structure
        docData = {
          title: `${project.name} Documentation`,
          content: rawContent,
          sections: []
        };
      }
    } else {
      // Create basic fallback
      docData = {
        title: `${project.name} Documentation`,
        content: `# ${project.name}\n\n${analysis.summary || "Documentation for this repository."}`,
        sections: []
      };
    }
  }

  return {
    projectId: project.id,
    title: docData.title || `${project.name} Documentation`,
    content: docData.content || analysis.summary || "",
    sections: docData.sections || [],
  };
}

export async function transcribeAudio(audioBuffer: Buffer): Promise<string> {
  const { toFile } = await import("openai");
  const file = await toFile(audioBuffer, "audio.webm");
  
  const response = await openai.audio.transcriptions.create({
    file,
    model: "gpt-4o-mini-transcribe",
  });
  
  return response.text;
}

export async function generateBRD(
  featureRequest: FeatureRequest,
  analysis: RepoAnalysis | null,
  onChunk?: (chunk: string) => void
): Promise<Omit<BRD, "id" | "createdAt" | "updatedAt">> {
  const contextInfo = analysis
    ? `
Repository Context:
- Architecture: ${analysis.architecture}
- Tech Stack: ${JSON.stringify(analysis.techStack)}
- Existing Features: ${analysis.features?.map(f => f.name).join(", ")}
- Testing Framework: ${analysis.testingFramework || "Not specified"}
`
    : "";

  const stream = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `You are a senior business analyst creating a Business Requirements Document (BRD). Generate a comprehensive, professional BRD based on the feature request and repository context.

Return a JSON object with this structure:
{
  "title": "BRD title",
  "version": "1.0",
  "status": "draft",
  "content": {
    "overview": "Executive summary of the feature",
    "objectives": ["List of business objectives"],
    "scope": {
      "inScope": ["What's included"],
      "outOfScope": ["What's excluded"]
    },
    "functionalRequirements": [
      {
        "id": "FR-001",
        "title": "Requirement title",
        "description": "Detailed description",
        "priority": "high|medium|low",
        "acceptanceCriteria": ["List of criteria"]
      }
    ],
    "nonFunctionalRequirements": [
      {
        "id": "NFR-001",
        "category": "Performance|Security|Scalability|etc",
        "description": "Requirement description"
      }
    ],
    "technicalConsiderations": ["Technical notes aligned with existing stack"],
    "dependencies": ["List of dependencies"],
    "assumptions": ["List of assumptions"],
    "risks": [
      {
        "description": "Risk description",
        "mitigation": "How to mitigate"
      }
    ]
  }
}`
      },
      {
        role: "user",
        content: `Create a BRD for this feature request:

Title: ${featureRequest.title}
Description: ${featureRequest.description}

${contextInfo}`
      }
    ],
    response_format: { type: "json_object" },
    max_completion_tokens: 4096,
    stream: true,
  });

  let fullContent = "";
  
  for await (const chunk of stream) {
    const content = chunk.choices[0]?.delta?.content || "";
    if (content) {
      fullContent += content;
      onChunk?.(content);
    }
  }
  
  // Robust JSON parsing with fallback
  let brdData: any;
  try {
    brdData = JSON.parse(fullContent);
  } catch (parseError) {
    console.error("Failed to parse BRD JSON, attempting recovery:", parseError);
    // Try to extract JSON from the content
    const jsonMatch = fullContent.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        brdData = JSON.parse(jsonMatch[0]);
      } catch {
        throw new Error("Failed to parse BRD response as JSON");
      }
    } else {
      throw new Error("No valid JSON found in BRD response");
    }
  }
  
  // Validate required fields with defaults
  const brdContent = brdData.content || {};
  
  return {
    projectId: featureRequest.projectId,
    featureRequestId: featureRequest.id,
    title: brdData.title || featureRequest.title,
    version: brdData.version || "1.0",
    status: "draft",
    content: {
      overview: brdContent.overview || featureRequest.description,
      objectives: brdContent.objectives || [],
      scope: brdContent.scope || { inScope: [], outOfScope: [] },
      functionalRequirements: brdContent.functionalRequirements || [],
      nonFunctionalRequirements: brdContent.nonFunctionalRequirements || [],
      technicalConsiderations: brdContent.technicalConsiderations || [],
      dependencies: brdContent.dependencies || [],
      assumptions: brdContent.assumptions || [],
      risks: brdContent.risks || [],
    },
  };
}

export async function generateTestCases(
  brd: BRD,
  analysis: RepoAnalysis | null
): Promise<Omit<TestCase, "id" | "createdAt">[]> {
  const testingContext = analysis?.testingFramework
    ? `Use ${analysis.testingFramework} syntax for code snippets.`
    : "Use Jest with TypeScript for code snippets.";

  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `You are a senior QA engineer creating comprehensive test cases from a BRD. Generate test cases for each functional requirement.

${testingContext}

Return a JSON object with this structure:
{
  "testCases": [
    {
      "requirementId": "FR-001",
      "title": "Test case title",
      "description": "What this test validates",
      "type": "unit|integration|e2e|acceptance",
      "priority": "critical|high|medium|low",
      "preconditions": ["List of preconditions"],
      "steps": [
        {
          "step": 1,
          "action": "What to do",
          "expectedResult": "What should happen"
        }
      ],
      "expectedOutcome": "Overall expected result",
      "codeSnippet": "Optional code example for automated testing"
    }
  ]
}`
      },
      {
        role: "user",
        content: `Generate test cases for this BRD:

Title: ${brd.title}
Functional Requirements:
${JSON.stringify(brd.content.functionalRequirements, null, 2)}

Non-Functional Requirements:
${JSON.stringify(brd.content.nonFunctionalRequirements, null, 2)}`
      }
    ],
    response_format: { type: "json_object" },
    max_completion_tokens: 4096,
  });

  const content = response.choices[0]?.message?.content || '{"testCases":[]}';
  const data = JSON.parse(content);
  
  return data.testCases.map((tc: any, index: number) => ({
    brdId: brd.id,
    requirementId: tc.requirementId || `FR-${String(index + 1).padStart(3, "0")}`,
    title: tc.title,
    description: tc.description,
    type: tc.type || "e2e",
    priority: tc.priority || "medium",
    preconditions: tc.preconditions || [],
    steps: tc.steps || [],
    expectedOutcome: tc.expectedOutcome,
    codeSnippet: tc.codeSnippet,
  }));
}

export async function generateTestData(
  testCases: TestCase[],
  brd: BRD
): Promise<Omit<TestData, "id" | "createdAt">[]> {
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `You are a senior QA engineer creating test data for test cases. Generate comprehensive test datasets including valid, invalid, edge, and boundary cases.

Return a JSON object with this structure:
{
  "testData": [
    {
      "testCaseId": "The test case this data is for",
      "name": "Descriptive name for this dataset",
      "description": "What this test data represents",
      "dataType": "valid|invalid|edge|boundary",
      "data": {
        "Any relevant test data as key-value pairs"
      }
    }
  ]
}`
      },
      {
        role: "user",
        content: `Generate test data for these test cases:

BRD Title: ${brd.title}
Test Cases:
${testCases.map(tc => `- ${tc.id || tc.title}: ${tc.description}`).join("\n")}

Requirements context:
${JSON.stringify(brd.content.functionalRequirements.slice(0, 3), null, 2)}`
      }
    ],
    response_format: { type: "json_object" },
    max_completion_tokens: 4096,
  });

  const content = response.choices[0]?.message?.content || '{"testData":[]}';
  const data = JSON.parse(content);
  
  return data.testData.map((td: any) => ({
    testCaseId: td.testCaseId || testCases[0]?.id || "TC-001",
    name: td.name,
    description: td.description,
    dataType: td.dataType || "valid",
    data: td.data || {},
  }));
}
