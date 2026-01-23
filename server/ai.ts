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
    
    // Get all files for structure
    const allFiles = treeData.tree
      ?.filter((f: any) => f.type === "blob")
      .map((f: any) => f.path) || [];
    
    // Identify important files to fetch (config, entry points, components, services)
    const priorityPatterns = [
      /^package\.json$/,
      /^README\.md$/i,
      /^\.env\.example$/,
      /^tsconfig\.json$/,
      /^vite\.config\.(ts|js)$/,
      /^next\.config\.(js|mjs|ts)$/,
      /^app\.(tsx?|jsx?)$/,
      /^index\.(tsx?|jsx?)$/,
      /^main\.(tsx?|jsx?)$/,
      /src\/index\.(tsx?|jsx?)$/,
      /src\/App\.(tsx?|jsx?)$/,
      /src\/main\.(tsx?|jsx?)$/,
      /pages\/index\.(tsx?|jsx?)$/,
      /pages\/_app\.(tsx?|jsx?)$/,
      /components\/.*\.(tsx?|jsx?)$/,
      /services\/.*\.(tsx?|js)$/,
      /hooks\/.*\.(tsx?|js)$/,
      /utils\/.*\.(tsx?|js)$/,
      /lib\/.*\.(tsx?|js)$/,
      /api\/.*\.(tsx?|js)$/,
      /routes\/.*\.(tsx?|js)$/,
      /models\/.*\.(tsx?|js)$/,
      /controllers\/.*\.(tsx?|js)$/,
    ];
    
    // Find files matching priority patterns
    const filesToFetch: string[] = [];
    for (const file of allFiles) {
      if (priorityPatterns.some(pattern => pattern.test(file))) {
        filesToFetch.push(file);
      }
    }
    
    // Limit to prevent rate limiting (fetch up to 25 important files)
    const limitedFiles = filesToFetch.slice(0, 25);
    
    // Fetch file contents in parallel with rate limiting
    const fileContents: string[] = [];
    const fetchFile = async (filePath: string): Promise<string | null> => {
      try {
        const contentResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${filePath}`);
        if (contentResponse.ok) {
          const contentData = await contentResponse.json();
          if (contentData.content) {
            const decoded = Buffer.from(contentData.content, "base64").toString("utf-8");
            // Limit individual file content to 2000 chars for context window
            const truncated = decoded.length > 2000 ? decoded.substring(0, 2000) + "\n... [truncated]" : decoded;
            return `--- ${filePath} ---\n${truncated}\n`;
          }
        }
      } catch {
        // File fetch failed, skip
      }
      return null;
    };
    
    // Batch fetch files (5 at a time to avoid rate limiting)
    for (let i = 0; i < limitedFiles.length; i += 5) {
      const batch = limitedFiles.slice(i, i + 5);
      const results = await Promise.all(batch.map(fetchFile));
      results.forEach(r => r && fileContents.push(r));
    }
    
    // Group files by directory for better structure understanding
    const dirStructure: Record<string, string[]> = {};
    for (const file of allFiles) {
      const parts = file.split("/");
      const dir = parts.length > 1 ? parts.slice(0, -1).join("/") : "(root)";
      if (!dirStructure[dir]) dirStructure[dir] = [];
      dirStructure[dir].push(parts[parts.length - 1]);
    }
    
    const structureText = Object.entries(dirStructure)
      .map(([dir, files]) => `${dir}/\n  ${files.join("\n  ")}`)
      .join("\n\n");
    
    return `
Repository: ${repoData.full_name}
Description: ${repoData.description || "No description"}
Primary Language: ${repoData.language || "Unknown"}
Stars: ${repoData.stargazers_count}
Topics: ${repoData.topics?.join(", ") || "None"}
Default Branch: ${repoData.default_branch || "main"}

=== DIRECTORY STRUCTURE ===
${structureText}

=== FILE CONTENTS ===
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
        content: `You are a senior software architect analyzing GitHub repositories. Carefully examine ALL provided file contents, directory structure, and code to generate an ACCURATE and DETAILED analysis.

IMPORTANT INSTRUCTIONS:
1. Read EVERY file content provided - each file reveals important details
2. Extract EXACT feature names, component names, and function names from the actual code
3. Identify the REAL purpose from the code logic, not generic descriptions
4. List ACTUAL dependencies from package.json or similar config files
5. Describe the SPECIFIC architecture based on the directory structure and imports
6. Do NOT make up features that don't exist in the code
7. Do NOT use generic descriptions - be specific to THIS repository

Return your analysis as a JSON object with this exact structure:
{
  "summary": "Specific description of what this application does based on the actual code",
  "architecture": "Detailed description of the architectural patterns observed in the code structure",
  "features": [
    {
      "name": "Actual feature name from the code",
      "description": "What this feature does based on examining the code",
      "files": ["actual/file/paths.tsx", "from/the/repo.ts"]
    }
  ],
  "techStack": {
    "languages": ["languages from package.json/actual files"],
    "frameworks": ["exact framework names and versions from dependencies"],
    "databases": ["databases if referenced in code"],
    "tools": ["actual tools found in config files"]
  },
  "testingFramework": "Testing framework from devDependencies if any",
  "codePatterns": ["patterns actually observed in the code like hooks, components, services, etc"]
}`
      },
      {
        role: "user",
        content: `Analyze this repository carefully. Read all file contents and provide an accurate analysis:\n\n${repoContext}`
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
        content: `You are a technical writer creating ACCURATE and DETAILED documentation for a software project. Generate documentation that is SPECIFIC to this project based on the analysis provided.

IMPORTANT INSTRUCTIONS:
1. Use EXACT names from the analysis - component names, feature names, file paths
2. Document the ACTUAL features identified in the analysis
3. Include REAL technical details from the tech stack
4. Do NOT add generic content that doesn't apply to this specific project
5. Reference ACTUAL file paths and component names from the analysis
6. Keep descriptions accurate to what the code actually does

Return a JSON object with this structure:
{
  "title": "Project Name - Technical Documentation",
  "content": "Full markdown overview of the project",
  "sections": [
    {
      "title": "Overview",
      "content": "Detailed markdown describing what this specific project does"
    },
    {
      "title": "Architecture",
      "content": "The actual architecture pattern used with specific file/folder references"
    },
    {
      "title": "Features",
      "content": "Each feature with its actual implementation details"
    },
    {
      "title": "Technology Stack",
      "content": "Exact technologies with versions where available"
    },
    {
      "title": "Getting Started",
      "content": "How to run this specific project based on its configuration"
    },
    {
      "title": "Project Structure",
      "content": "Key files and directories with their purposes"
    }
  ]
}`
      },
      {
        role: "user",
        content: `Generate accurate technical documentation for this project:

Project Name: ${project.name}
Repository URL: ${project.repoUrl}

Analysis (use these EXACT details in your documentation):
- Summary: ${analysis.summary}
- Architecture: ${analysis.architecture}
- Tech Stack: ${JSON.stringify(analysis.techStack, null, 2)}
- Features: ${JSON.stringify(analysis.features, null, 2)}
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
