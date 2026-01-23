import OpenAI from "openai";
import type { RepoAnalysis, FeatureRequest, BRD, TestCase, TestData, Documentation, Project } from "@shared/schema";

const openai = new OpenAI({
  apiKey: process.env.AI_INTEGRATIONS_OPENAI_API_KEY,
  baseURL: process.env.AI_INTEGRATIONS_OPENAI_BASE_URL,
});

// GitHub API headers with authentication
function getGitHubHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "DocuGen-AI",
  };
  
  const token = process.env.GITHUB_PERSONAL_ACCESS_TOKEN;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  
  return headers;
}

// Fetch repository contents from GitHub with authentication
async function fetchRepoContents(repoUrl: string): Promise<string> {
  const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!match) throw new Error("Invalid GitHub URL");
  
  const owner = match[1];
  const repo = match[2].replace(/\.git$/, "");
  const headers = getGitHubHeaders();
  
  try {
    // Fetch repository info
    const repoResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}`, { headers });
    if (!repoResponse.ok) throw new Error(`Failed to fetch repository: ${repoResponse.status}`);
    const repoData = await repoResponse.json();
    
    const defaultBranch = repoData.default_branch || "main";
    
    // Fetch file tree with authentication
    let treeData: any = { tree: [] };
    const treeResponse = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/git/trees/${defaultBranch}?recursive=1`,
      { headers }
    );
    if (treeResponse.ok) {
      treeData = await treeResponse.json();
    }
    
    // Get all code files (exclude images, binaries, etc.)
    const codeExtensions = [
      '.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.go', '.rs', '.rb', '.php',
      '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
      '.json', '.yaml', '.yml', '.toml', '.xml', '.md', '.txt',
      '.sql', '.graphql', '.prisma', '.env.example', '.gitignore',
      '.sh', '.bash', '.zsh', '.dockerfile', '.config.js', '.config.ts'
    ];
    
    const allFiles = treeData.tree
      ?.filter((f: any) => {
        if (f.type !== "blob") return false;
        const path = f.path.toLowerCase();
        // Exclude node_modules, dist, build, etc.
        if (path.includes('node_modules/') || path.includes('/dist/') || 
            path.includes('/build/') || path.includes('/.git/') ||
            path.includes('/coverage/') || path.includes('/.next/')) {
          return false;
        }
        // Include files with code extensions or no extension (like Dockerfile)
        return codeExtensions.some(ext => path.endsWith(ext)) || 
               !path.includes('.') ||
               path.endsWith('dockerfile') ||
               path.endsWith('makefile');
      })
      .map((f: any) => ({ path: f.path, size: f.size || 0 })) || [];
    
    // Sort files by importance
    const priorityOrder = (path: string): number => {
      const lower = path.toLowerCase();
      if (lower === 'readme.md') return 0;
      if (lower === 'package.json') return 1;
      if (lower.includes('index.') || lower.includes('main.') || lower.includes('app.')) return 2;
      if (lower.startsWith('src/')) return 3;
      if (lower.includes('/components/')) return 4;
      if (lower.includes('/pages/')) return 5;
      if (lower.includes('/api/') || lower.includes('/routes/')) return 6;
      if (lower.includes('/services/') || lower.includes('/hooks/')) return 7;
      if (lower.includes('/utils/') || lower.includes('/lib/')) return 8;
      if (lower.includes('config')) return 9;
      return 10;
    };
    
    allFiles.sort((a: any, b: any) => priorityOrder(a.path) - priorityOrder(b.path));
    
    // Fetch ALL important files (up to 50 files, max 3000 chars each)
    const filesToFetch = allFiles.slice(0, 50);
    const fileContents: string[] = [];
    let totalChars = 0;
    const maxTotalChars = 100000; // Limit total context to ~100k chars
    
    const fetchFile = async (filePath: string): Promise<{ path: string; content: string } | null> => {
      try {
        const contentResponse = await fetch(
          `https://api.github.com/repos/${owner}/${repo}/contents/${filePath}`,
          { headers }
        );
        if (contentResponse.ok) {
          const contentData = await contentResponse.json();
          if (contentData.content) {
            const decoded = Buffer.from(contentData.content, "base64").toString("utf-8");
            return { path: filePath, content: decoded };
          }
        }
      } catch (err) {
        console.error(`Error fetching ${filePath}:`, err);
      }
      return null;
    };
    
    // Batch fetch files (10 at a time for authenticated requests)
    for (let i = 0; i < filesToFetch.length && totalChars < maxTotalChars; i += 10) {
      const batch = filesToFetch.slice(i, i + 10);
      const results = await Promise.all(batch.map((f: any) => fetchFile(f.path)));
      
      for (const result of results) {
        if (result && totalChars < maxTotalChars) {
          // Truncate large files but keep enough context
          const maxFileChars = 4000;
          const content = result.content.length > maxFileChars 
            ? result.content.substring(0, maxFileChars) + "\n... [truncated - file continues]"
            : result.content;
          
          fileContents.push(`\n=== FILE: ${result.path} ===\n${content}`);
          totalChars += content.length;
        }
      }
    }
    
    // Build comprehensive directory structure
    const dirStructure: Record<string, string[]> = {};
    for (const file of allFiles) {
      const parts = file.path.split("/");
      const dir = parts.length > 1 ? parts.slice(0, -1).join("/") : "(root)";
      if (!dirStructure[dir]) dirStructure[dir] = [];
      dirStructure[dir].push(parts[parts.length - 1]);
    }
    
    const structureText = Object.entries(dirStructure)
      .slice(0, 30) // Limit directories shown
      .map(([dir, files]) => `${dir}/\n  ${files.slice(0, 20).join("\n  ")}${files.length > 20 ? `\n  ... and ${files.length - 20} more files` : ""}`)
      .join("\n\n");
    
    console.log(`Fetched ${fileContents.length} files, ${totalChars} total characters for ${owner}/${repo}`);
    
    return `
=== REPOSITORY INFORMATION ===
Repository: ${repoData.full_name}
Description: ${repoData.description || "No description provided"}
Primary Language: ${repoData.language || "Unknown"}
Stars: ${repoData.stargazers_count}
Forks: ${repoData.forks_count}
Topics: ${repoData.topics?.join(", ") || "None"}
Default Branch: ${defaultBranch}
License: ${repoData.license?.name || "Not specified"}
Total Files Analyzed: ${fileContents.length}

=== DIRECTORY STRUCTURE ===
${structureText}

=== COMPLETE FILE CONTENTS ===
${fileContents.join("\n")}
    `.trim();
  } catch (error) {
    console.error("Error fetching repo contents:", error);
    throw new Error(`Failed to fetch repository: ${error instanceof Error ? error.message : "Unknown error"}`);
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
  // Fetch raw repository contents again for accurate documentation
  let repoContext = "";
  try {
    repoContext = await fetchRepoContents(project.repoUrl);
    console.log(`Documentation: Re-fetched repo contents for ${project.name}`);
  } catch (err) {
    console.error("Failed to fetch repo for documentation:", err);
  }
  
  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `You are a technical writer creating ACCURATE and DETAILED documentation for a software project. You have access to the ACTUAL SOURCE CODE files. Read them carefully and generate documentation that EXACTLY matches what the code does.

CRITICAL INSTRUCTIONS:
1. READ the actual file contents provided - they contain the real implementation
2. Extract EXACT component names, function names, and features from the code
3. Document what each file ACTUALLY does based on its code
4. Include REAL dependencies from package.json
5. Do NOT invent features that don't exist in the code
6. Do NOT use placeholder or example content - everything must come from the actual code
7. If you see a component like "CardOnboarding" in the code, document "CardOnboarding" - not a generic name

Return a JSON object with this structure:
{
  "title": "Project Name - Technical Documentation",
  "content": "Full markdown overview based on actual code",
  "sections": [
    {
      "title": "Overview",
      "content": "Description based on README and actual code purpose"
    },
    {
      "title": "Architecture",
      "content": "Architecture based on actual file structure and imports"
    },
    {
      "title": "Features",
      "content": "Features extracted from actual components and functions in the code"
    },
    {
      "title": "Components",
      "content": "List of actual React/UI components found in the code with their purposes"
    },
    {
      "title": "Technology Stack",
      "content": "Technologies from package.json dependencies"
    },
    {
      "title": "API/Services",
      "content": "Any API endpoints or services found in the code"
    },
    {
      "title": "Getting Started",
      "content": "Based on package.json scripts and README"
    },
    {
      "title": "Project Structure",
      "content": "Actual file structure from the repository"
    }
  ]
}`
      },
      {
        role: "user",
        content: `Generate accurate technical documentation by reading the ACTUAL SOURCE CODE below.

Project Name: ${project.name}
Repository URL: ${project.repoUrl}

=== ACTUAL SOURCE CODE FILES ===
${repoContext}

=== ANALYSIS SUMMARY (for reference) ===
- Summary: ${analysis.summary}
- Tech Stack: ${JSON.stringify(analysis.techStack, null, 2)}
- Features Found: ${JSON.stringify(analysis.features, null, 2)}`
      }
    ],
    response_format: { type: "json_object" },
    max_completion_tokens: 8192,
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
