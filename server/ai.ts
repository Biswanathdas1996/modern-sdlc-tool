import type { RepoAnalysis, FeatureRequest, BRD, TestCase, TestData, Documentation, Project, UserStory, BPMNDiagram, DatabaseSchemaInfo } from "@shared/schema";

// PwC GenAI environment configuration
const GENAI_ENDPOINT = process.env.PWC_GENAI_ENDPOINT_URL!;
const API_KEY = process.env.PWC_GENAI_API_KEY!;
const BEARER_TOKEN = process.env.PWC_GENAI_BEARER_TOKEN!;

/**
 * Makes a prompt-based API call to PwC's internal GenAI service
 * using vertex_ai.gemini-2.0-flash model (text-only).
 *
 * @param prompt The input prompt to send to the AI model
 * @param options Optional parameters for the API call
 * @returns The text content from the GenAI API response
 */
async function callPwcGenAI(prompt: string, options: { temperature?: number; maxTokens?: number } = {}): Promise<string> {
  if (!API_KEY || !BEARER_TOKEN || !GENAI_ENDPOINT) {
    throw new Error(
      "PwC GenAI credentials not configured. Please provide PWC_GENAI_API_KEY, PWC_GENAI_BEARER_TOKEN, and PWC_GENAI_ENDPOINT_URL.",
    );
  }

  const requestBody = JSON.stringify({
    model: "vertex_ai.gemini-2.0-flash",
    prompt,
    temperature: options.temperature ?? 0.7,
    top_p: 1,
    presence_penalty: 0,
    stream: false,
    stream_options: null,
    seed: 25,
    stop: null,
  });

  const headers = {
    accept: "application/json",
    "API-Key": API_KEY,
    Authorization: `Bearer ${BEARER_TOKEN}`,
    "Content-Type": "application/json",
  };

  console.log("Calling PwC GenAI with prompt length:", prompt.length);

  const response = await fetch(GENAI_ENDPOINT, {
    method: "POST",
    headers,
    body: requestBody,
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error("PwC GenAI API error:", {
      status: response.status,
      error: errorText,
    });
    throw new Error(`PwC GenAI API Error: ${response.status} - ${errorText}`);
  }

  const result = await response.json();
  console.log("PwC GenAI API response received:", {
    keys: Object.keys(result),
  });

  // Extract text from the response - handle different response formats
  if (result.choices && result.choices[0]) {
    const choice = result.choices[0];
    if (choice.message?.content) {
      return choice.message.content;
    }
    if (choice.text) {
      return choice.text;
    }
  }
  if (result.text) {
    return result.text;
  }
  if (result.content) {
    return result.content;
  }
  
  throw new Error("Unexpected response format from PwC GenAI API");
}

/**
 * Helper function to build a prompt from system and user messages
 */
function buildPrompt(systemMessage: string, userMessage: string): string {
  return `System: ${systemMessage}\n\nUser: ${userMessage}`;
}

/**
 * Helper to parse JSON from AI response, handling markdown code blocks
 * with robust fallback for extracting JSON from mixed content
 */
function parseJsonResponse(text: string): any {
  // First attempt: Remove markdown code blocks if present
  let cleaned = text.trim();
  if (cleaned.startsWith("```json")) {
    cleaned = cleaned.slice(7);
  } else if (cleaned.startsWith("```")) {
    cleaned = cleaned.slice(3);
  }
  if (cleaned.endsWith("```")) {
    cleaned = cleaned.slice(0, -3);
  }
  
  try {
    return JSON.parse(cleaned.trim());
  } catch (firstError) {
    // Fallback: Try to extract JSON object/array using regex
    console.log("First JSON parse failed, attempting regex extraction...");
    
    // Try to find a JSON object
    const objectMatch = text.match(/\{[\s\S]*\}/);
    if (objectMatch) {
      try {
        return JSON.parse(objectMatch[0]);
      } catch {
        // Continue to array match
      }
    }
    
    // Try to find a JSON array
    const arrayMatch = text.match(/\[[\s\S]*\]/);
    if (arrayMatch) {
      try {
        return JSON.parse(arrayMatch[0]);
      } catch {
        // Continue to throw
      }
    }
    
    // If all attempts fail, throw the original error with context
    throw new Error(`Failed to parse JSON from response. Original error: ${firstError}. Response preview: ${text.slice(0, 200)}...`);
  }
}

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
  
  const systemPrompt = `You are a senior software architect analyzing GitHub repositories. Carefully examine ALL provided file contents, directory structure, and code to generate an ACCURATE and DETAILED analysis.

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
}`;

  const userPrompt = `Analyze this repository carefully. Read all file contents and provide an accurate analysis:\n\n${repoContext}`;
  
  const prompt = buildPrompt(systemPrompt, userPrompt);
  const responseText = await callPwcGenAI(prompt);
  
  const content = responseText || "{}";
  const analysisData = parseJsonResponse(content);
  
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
  
  const systemPrompt = `You are a technical writer creating ACCURATE and DETAILED documentation for a software project. You have access to the ACTUAL SOURCE CODE files. Read them carefully and generate documentation that EXACTLY matches what the code does.

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
}`;

  const userPrompt = `Generate accurate technical documentation by reading the ACTUAL SOURCE CODE below.

Project Name: ${project.name}
Repository URL: ${project.repoUrl}

=== ACTUAL SOURCE CODE FILES ===
${repoContext}

=== ANALYSIS SUMMARY (for reference) ===
- Summary: ${analysis.summary}
- Tech Stack: ${JSON.stringify(analysis.techStack, null, 2)}
- Features Found: ${JSON.stringify(analysis.features, null, 2)}`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const rawContent = await callPwcGenAI(prompt);
  
  // Robust JSON parsing with fallback
  let docData: any;
  try {
    docData = parseJsonResponse(rawContent);
  } catch (parseError) {
    console.error("Failed to parse documentation JSON, attempting recovery:", parseError);
    // Create basic fallback
    docData = {
      title: `${project.name} Documentation`,
      content: `# ${project.name}\n\n${analysis.summary || "Documentation for this repository."}`,
      sections: []
    };
  }

  return {
    projectId: project.id,
    title: docData.title || `${project.name} Documentation`,
    content: docData.content || analysis.summary || "",
    sections: docData.sections || [],
  };
}

export async function generateBPMNDiagram(
  documentation: Documentation,
  analysis: RepoAnalysis
): Promise<Omit<BPMNDiagram, "id" | "createdAt">> {
  const systemPrompt = `You are an expert at creating professional BPMN-style business flow diagrams using Mermaid.js flowchart syntax.

Create a SINGLE comprehensive flowchart that shows the ENTIRE business flow of the application from start to finish.

STRICT MERMAID SYNTAX RULES - FOLLOW EXACTLY:
1. Start with exactly: flowchart TD
2. Node definitions - NEVER use parentheses, quotes, or special chars in labels:
   - Start/End terminals: A([Start]) or Z([End])
   - Process boxes: B[Process Name]
   - Decision diamonds: C{Is Valid}
   - Database/Storage: D[(Database)]
3. Subgraph syntax:
   - subgraph SubgraphID[Display Name]
   - end
4. Arrow connections:
   - Simple: A --> B
   - With label: A -->|Yes| B
5. Keep labels SHORT: 2-4 words maximum, no special characters
6. Use simple alphanumeric IDs: A, B, C1, C2, etc.

PROFESSIONAL DIAGRAM STRUCTURE:
1. Clear entry point with user action
2. Major workflow stages organized as subgraphs
3. Decision points with Yes/No branches
4. Data storage and API interactions shown
5. Output states and completion points

VALID EXAMPLE:
flowchart TD
    subgraph Init[Getting Started]
        A([User Opens App]) --> B[Load Dashboard]
    end
    subgraph Process[Main Process]
        B --> C{Has Data}
        C -->|Yes| D[Display Results]
        C -->|No| E[Show Empty State]
    end
    subgraph Complete[Completion]
        D --> F([Done])
        E --> F
    end

Return JSON:
{
  "diagrams": [
    {
      "featureName": "Complete Business Flow",
      "description": "End-to-end business process showing the complete user journey",
      "mermaidCode": "flowchart TD\\n    subgraph Init[Getting Started]\\n        A([Start]) --> B[Load Data]\\n    end"
    }
  ]
}

CRITICAL:
- ONE comprehensive diagram only
- NO parentheses or special chars inside node labels
- NO colons inside labels
- Short readable labels
- Valid Mermaid syntax that will render correctly`;

  const userPrompt = `Generate a SINGLE comprehensive BPMN-style diagram showing the COMPLETE business flow of this application.

=== APPLICATION OVERVIEW ===
Title: ${documentation.title}
${documentation.sections.map(s => `## ${s.title}\n${s.content}`).join('\n\n')}

=== ALL FEATURES ===
${JSON.stringify(analysis.features, null, 2)}

Create ONE comprehensive diagram that shows how a user progresses through the entire application workflow, from initial entry through all stages to final outputs. Use subgraphs to organize the flow by major stages/features.`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const rawContent = await callPwcGenAI(prompt);
  
  let diagramData: any;
  try {
    diagramData = parseJsonResponse(rawContent);
  } catch (parseError) {
    console.error("Failed to parse BPMN diagram JSON:", parseError);
    diagramData = { diagrams: [] };
  }

  return {
    projectId: documentation.projectId,
    documentationId: documentation.id,
    diagrams: diagramData.diagrams || [],
  };
}

export async function transcribeAudio(audioBuffer: Buffer): Promise<string> {
  // Audio transcription is not available with PWC GenAI
  // This would require a separate speech-to-text service
  throw new Error("Audio transcription is not currently available. Please use text input instead.");
}

export async function generateBRD(
  featureRequest: FeatureRequest,
  analysis: RepoAnalysis | null,
  documentation: Documentation | null,
  databaseSchema: DatabaseSchemaInfo | null,
  knowledgeContext: string | null,
  onChunk?: (chunk: string) => void
): Promise<Omit<BRD, "id" | "createdAt" | "updatedAt">> {
  // Build comprehensive context from documentation (primary) and analysis (fallback)
  let documentationContext = "";
  
  // Build knowledge base context if available
  let knowledgeBaseContext = "";
  if (knowledgeContext) {
    knowledgeBaseContext = `
=== KNOWLEDGE BASE (Relevant Documents) ===
The following information was retrieved from uploaded documents in the knowledge base.
Use this context to inform your BRD generation with domain-specific knowledge.

${knowledgeContext}

=== END KNOWLEDGE BASE ===
`;
  }
  
  // Build database schema context if available
  let databaseSchemaContext = "";
  if (databaseSchema) {
    const tableDescriptions = databaseSchema.tables.map(table => {
      const columns = table.columns.map(col => {
        let desc = `    - ${col.name}: ${col.dataType}`;
        if (col.isPrimaryKey) desc += " (PK)";
        if (col.isForeignKey) desc += ` (FK -> ${col.references || "?"})`;
        if (!col.isNullable) desc += " NOT NULL";
        return desc;
      }).join("\n");
      return `  ${table.name} (${table.rowCount?.toLocaleString() || 0} rows):\n${columns}`;
    }).join("\n\n");
    
    databaseSchemaContext = `
=== CONNECTED DATABASE SCHEMA ===
Database: ${databaseSchema.databaseName}
Tables: ${databaseSchema.tables.length}

${tableDescriptions}
=== END DATABASE SCHEMA ===
`;
  }
  
  if (documentation) {
    // Parse the content if it's a JSON string, otherwise use as-is
    let docContent: any = {};
    try {
      if (typeof documentation.content === 'string') {
        docContent = JSON.parse(documentation.content);
      } else {
        docContent = documentation.content;
      }
    } catch (e) {
      // If parsing fails, use the content as a string
      docContent = { overview: documentation.content };
    }
    
    documentationContext = `
=== TECHNICAL DOCUMENTATION (Generated from Repository Analysis) ===
This BRD is being generated based on the following technical documentation:

Project: ${documentation.title}

${docContent.overview ? `## Overview\n${docContent.overview}\n` : ""}

${docContent.architecture ? `## Architecture\n${docContent.architecture}\n` : ""}

${docContent.techStack ? `## Technology Stack\n${JSON.stringify(docContent.techStack, null, 2)}\n` : ""}

${docContent.components && docContent.components.length > 0 ? `## Components\n${docContent.components.map((c: any) => `- ${c.name}: ${c.description}`).join("\n")}\n` : ""}

${docContent.apiServices && docContent.apiServices.length > 0 ? `## API/Services\n${docContent.apiServices.map((a: any) => `- ${a.name}: ${a.description}`).join("\n")}\n` : ""}

${docContent.dataModels && docContent.dataModels.length > 0 ? `## Data Models\n${docContent.dataModels.map((d: any) => `- ${d.name}: ${d.description}`).join("\n")}\n` : ""}

${docContent.features && docContent.features.length > 0 ? `## Existing Features\n${docContent.features.map((f: any) => `- ${f.name}: ${f.description}`).join("\n")}\n` : ""}

${docContent.dependencies ? `## Dependencies\n${JSON.stringify(docContent.dependencies, null, 2)}\n` : ""}

${docContent.setupInstructions ? `## Setup Instructions\n${docContent.setupInstructions}\n` : ""}
=== END OF DOCUMENTATION ===
`;
  } else if (analysis) {
    // Fallback to analysis if no documentation
    documentationContext = `
Repository Context (from analysis):
- Architecture: ${analysis.architecture}
- Tech Stack: ${JSON.stringify(analysis.techStack)}
- Existing Features: ${analysis.features?.map(f => f.name).join(", ")}
- Testing Framework: ${analysis.testingFramework || "Not specified"}
`;
  }

  const systemPrompt = `You are a senior business analyst creating a Business Requirements Document (BRD). 

IMPORTANT: You are generating this BRD based on the TECHNICAL DOCUMENTATION that was generated from analyzing the repository${databaseSchema ? " AND the connected DATABASE SCHEMA" : ""}. 
Your BRD must:
1. Reference the existing components, APIs, and features from the documentation
2. Align technical considerations with the documented architecture and tech stack
3. Consider existing data models and dependencies
4. Build upon the documented features rather than reinventing them
${databaseSchema ? "5. Reference the database tables and their relationships when specifying data requirements\n6. Ensure data model changes are aligned with the existing database schema" : ""}

Return a JSON object with this structure:
{
  "title": "BRD title",
  "version": "1.0",
  "status": "draft",
  "sourceDocumentation": "Title of the source documentation this BRD is based on",
  "content": {
    "overview": "Executive summary - MUST mention this is based on the technical documentation analysis",
    "objectives": ["List of business objectives"],
    "scope": {
      "inScope": ["What's included - reference existing components where relevant"],
      "outOfScope": ["What's excluded"]
    },
    "existingSystemContext": {
      "relevantComponents": ["List existing components from docs that this feature will interact with"],
      "relevantAPIs": ["List existing APIs that will be extended or used"],
      "dataModelsAffected": ["List data models that will be modified or extended"]
    },
    "functionalRequirements": [
      {
        "id": "FR-001",
        "title": "Requirement title",
        "description": "Detailed description - reference existing components where applicable",
        "priority": "high|medium|low",
        "acceptanceCriteria": ["List of criteria"],
        "relatedComponents": ["Existing components this requirement affects"]
      }
    ],
    "nonFunctionalRequirements": [
      {
        "id": "NFR-001",
        "category": "Performance|Security|Scalability|etc",
        "description": "Requirement description"
      }
    ],
    "technicalConsiderations": ["Technical notes aligned with documented stack and architecture"],
    "dependencies": ["List of dependencies - include relevant documented dependencies"],
    "assumptions": ["List of assumptions based on the documentation"],
    "risks": [
      {
        "description": "Risk description",
        "mitigation": "How to mitigate"
      }
    ]
  }
}`;

  const userPrompt = `Create a BRD for this feature request. Make sure to thoroughly review the technical documentation${databaseSchema ? ", database schema" : ""}${knowledgeContext ? ", and knowledge base documents" : ""} and reference them in your requirements.

Feature Request:
Title: ${featureRequest.title}
Description: ${featureRequest.description}

${documentationContext}
${databaseSchemaContext}
${knowledgeBaseContext}`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const fullContent = await callPwcGenAI(prompt);
  
  // Send the full content as a single chunk for compatibility with existing frontend
  onChunk?.(fullContent);
  
  // Robust JSON parsing with fallback
  let brdData: any;
  try {
    brdData = parseJsonResponse(fullContent);
  } catch (parseError) {
    console.error("Failed to parse BRD JSON:", parseError);
    throw new Error("Failed to parse BRD response as JSON");
  }
  
  // Validate required fields with defaults
  const brdContent = brdData.content || {};
  
  return {
    projectId: featureRequest.projectId,
    featureRequestId: featureRequest.id,
    requestType: featureRequest.requestType || "feature",
    title: brdData.title || featureRequest.title,
    version: brdData.version || "1.0",
    status: "draft",
    sourceDocumentation: brdData.sourceDocumentation || (documentation?.title) || null,
    content: {
      overview: brdContent.overview || featureRequest.description,
      objectives: brdContent.objectives || [],
      scope: brdContent.scope || { inScope: [], outOfScope: [] },
      existingSystemContext: brdContent.existingSystemContext || null,
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
  analysis: RepoAnalysis | null,
  documentation: Documentation | null
): Promise<Omit<TestCase, "id" | "createdAt">[]> {
  const testingContext = analysis?.testingFramework
    ? `Use ${analysis.testingFramework} syntax for code snippets.`
    : "Use Jest with TypeScript for code snippets.";

  // Build documentation context for test cases
  let documentationContext = "";
  if (documentation) {
    let docContent: any = {};
    try {
      if (typeof documentation.content === 'string') {
        docContent = JSON.parse(documentation.content);
      } else {
        docContent = documentation.content;
      }
    } catch (e) {
      docContent = { overview: documentation.content };
    }
    
    documentationContext = `
=== REPOSITORY DOCUMENTATION (Use this as the authoritative source for test context) ===

${docContent.overview ? `## System Overview\n${docContent.overview}\n` : ""}

${docContent.architecture ? `## Architecture\n${docContent.architecture}\n` : ""}

${docContent.components && docContent.components.length > 0 ? `## Components to Test Against\n${docContent.components.map((c: any) => `- ${c.name}: ${c.description}${c.filePath ? ` (${c.filePath})` : ""}`).join("\n")}\n` : ""}

${docContent.apiServices && docContent.apiServices.length > 0 ? `## API Endpoints to Test\n${docContent.apiServices.map((a: any) => `- ${a.name}: ${a.description}${a.endpoint ? ` [${a.method || 'GET'} ${a.endpoint}]` : ""}`).join("\n")}\n` : ""}

${docContent.dataModels && docContent.dataModels.length > 0 ? `## Data Models (for test data structure)\n${docContent.dataModels.map((d: any) => `- ${d.name}: ${d.description}${d.fields ? ` - Fields: ${JSON.stringify(d.fields)}` : ""}`).join("\n")}\n` : ""}

${docContent.features && docContent.features.length > 0 ? `## Existing Features\n${docContent.features.map((f: any) => `- ${f.name}: ${f.description}`).join("\n")}\n` : ""}

${docContent.techStack ? `## Technology Stack\n${JSON.stringify(docContent.techStack, null, 2)}\n` : ""}

=== END DOCUMENTATION ===
`;
  }

  const systemPrompt = `You are a senior QA engineer creating comprehensive test cases from a BRD. Generate test cases for each functional requirement organized into 4 CATEGORIES.

CRITICAL: Your test cases MUST be based on the repository documentation provided. Reference actual:
- API endpoints with their actual URL routes (e.g., /api/users, /dashboard, /login) - NOT file paths
- HTTP methods (GET, POST, PUT, DELETE) for API calls
- Data models with their actual field names
- Existing features that the new feature interacts with

${testingContext}

IMPORTANT FOR TEST STEPS:
- Always use URL routes/endpoints (e.g., "Navigate to /dashboard", "POST to /api/auth/login")
- NEVER use file paths (e.g., do NOT write "client/src/pages/Dashboard.tsx")
- Be specific about URLs: "/api/users/123" not "the users endpoint"
- Include query parameters when relevant: "/api/products?category=electronics"

TEST CASE CATEGORIES (Generate test cases for EACH category):

1. **happy_path** - Standard successful scenarios where everything works as expected
   - Normal user flows with valid data
   - Expected successful outcomes
   - Primary use cases

2. **edge_case** - Boundary conditions and unusual but valid scenarios
   - Maximum/minimum values
   - Empty or null inputs (when valid)
   - Special characters, unicode, long strings
   - Concurrent operations
   - Timeout scenarios

3. **negative** - Error handling and invalid input scenarios
   - Invalid data formats
   - Missing required fields
   - Unauthorized access attempts
   - Invalid credentials
   - Rate limiting
   - Resource not found scenarios

4. **e2e** - Complete user journey tests spanning multiple features
   - Full workflow from start to finish
   - Cross-feature interactions
   - Real-world usage scenarios
   - Performance under realistic conditions

Return a JSON object with this structure:
{
  "testCases": [
    {
      "requirementId": "FR-001",
      "title": "Test case title",
      "description": "What this test validates",
      "category": "happy_path|edge_case|negative|e2e",
      "type": "unit|integration|e2e|acceptance",
      "priority": "critical|high|medium|low",
      "preconditions": ["List of preconditions"],
      "steps": [
        {
          "step": 1,
          "action": "Navigate to /route or Call POST /api/endpoint with payload",
          "expectedResult": "What should happen"
        }
      ],
      "expectedOutcome": "Overall expected result",
      "codeSnippet": "Optional code example for automated testing",
      "relatedComponents": ["List of UI components this test covers"],
      "relatedAPIs": ["List of API routes (URLs) this test covers, e.g., GET /api/users"]
    }
  ]
}

IMPORTANT: Generate at least 2-3 test cases for EACH category (happy_path, edge_case, negative, e2e) per requirement.`;

  const userPrompt = `Generate test cases for this BRD based on the repository documentation:

${documentationContext}

=== BRD TO CREATE TEST CASES FOR ===
Title: ${brd.title}

Functional Requirements:
${JSON.stringify(brd.content.functionalRequirements, null, 2)}

Non-Functional Requirements:
${JSON.stringify(brd.content.nonFunctionalRequirements, null, 2)}

${brd.content.existingSystemContext ? `
Existing System Context (from BRD):
- Relevant Components: ${brd.content.existingSystemContext.relevantComponents?.join(", ") || "None specified"}
- Relevant APIs: ${brd.content.existingSystemContext.relevantAPIs?.join(", ") || "None specified"}
- Data Models Affected: ${brd.content.existingSystemContext.dataModelsAffected?.join(", ") || "None specified"}
` : ""}

IMPORTANT: 
1. Create test cases that reference the actual components, APIs, and data models from the documentation above. Do not use generic or placeholder names.
2. Generate test cases for ALL 4 CATEGORIES: happy_path, edge_case, negative, and e2e.`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const content = await callPwcGenAI(prompt);
  const data = parseJsonResponse(content);
  
  return data.testCases.map((tc: any, index: number) => ({
    brdId: brd.id,
    requirementId: tc.requirementId || `FR-${String(index + 1).padStart(3, "0")}`,
    title: tc.title,
    description: tc.description,
    category: tc.category || "happy_path",
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
  brd: BRD,
  documentation: Documentation | null
): Promise<Omit<TestData, "id" | "createdAt">[]> {
  // Build documentation context for test data
  let documentationContext = "";
  if (documentation) {
    let docContent: any = {};
    try {
      if (typeof documentation.content === 'string') {
        docContent = JSON.parse(documentation.content);
      } else {
        docContent = documentation.content;
      }
    } catch (e) {
      docContent = { overview: documentation.content };
    }
    
    documentationContext = `
=== REPOSITORY DOCUMENTATION (Use for realistic test data) ===

${docContent.dataModels && docContent.dataModels.length > 0 ? `## Data Models (use these field names and types)\n${docContent.dataModels.map((d: any) => `- ${d.name}: ${d.description}${d.fields ? `\n  Fields: ${JSON.stringify(d.fields, null, 2)}` : ""}`).join("\n")}\n` : ""}

${docContent.apiServices && docContent.apiServices.length > 0 ? `## API Endpoints (test data should match expected request/response formats)\n${docContent.apiServices.map((a: any) => `- ${a.name}: ${a.description}${a.endpoint ? ` [${a.method || 'GET'} ${a.endpoint}]` : ""}`).join("\n")}\n` : ""}

${docContent.components && docContent.components.length > 0 ? `## Components (for UI test data context)\n${docContent.components.map((c: any) => `- ${c.name}: ${c.description}`).join("\n")}\n` : ""}

=== END DOCUMENTATION ===
`;
  }

  const systemPrompt = `You are a senior QA engineer creating test data for test cases. Generate comprehensive test datasets including valid, invalid, edge, and boundary cases.

CRITICAL: Your test data MUST be based on the repository documentation provided. Use:
- Actual field names and types from documented data models
- Realistic values that match the documented API formats
- Data structures that align with the codebase

Return a JSON object with this structure:
{
  "testData": [
    {
      "testCaseId": "The test case this data is for",
      "name": "Descriptive name for this dataset",
      "description": "What this test data represents",
      "dataType": "valid|invalid|edge|boundary",
      "data": {
        "Use actual field names from documentation"
      }
    }
  ]
}`;

  const userPrompt = `Generate test data for these test cases based on the repository documentation:

${documentationContext}

=== TEST CASES TO GENERATE DATA FOR ===
BRD Title: ${brd.title}
Test Cases:
${testCases.map(tc => `- ${tc.id || tc.title}: ${tc.description}`).join("\n")}

Requirements context:
${JSON.stringify(brd.content.functionalRequirements.slice(0, 3), null, 2)}

IMPORTANT: Generate test data that uses actual field names and data structures from the documentation. Do not use generic placeholder names.`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const content = await callPwcGenAI(prompt);
  const data = parseJsonResponse(content);
  
  return data.testData.map((td: any) => ({
    testCaseId: td.testCaseId || testCases[0]?.id || "TC-001",
    name: td.name,
    description: td.description,
    dataType: td.dataType || "valid",
    data: td.data || {},
  }));
}

export async function generateUserStories(
  brd: BRD,
  documentation: Documentation | null,
  databaseSchema: DatabaseSchemaInfo | null,
  parentContext?: string | null,
  knowledgeContext?: string | null
): Promise<Omit<UserStory, "id" | "createdAt">[]> {
  // Build knowledge base context if available
  let knowledgeBaseContext = "";
  if (knowledgeContext) {
    knowledgeBaseContext = `
=== KNOWLEDGE BASE (Relevant Documents) ===
${knowledgeContext}
=== END KNOWLEDGE BASE ===
`;
  }

  // Build documentation context
  let documentationContext = "";
  if (documentation) {
    let docContent: any = {};
    try {
      if (typeof documentation.content === 'string') {
        docContent = JSON.parse(documentation.content);
      } else {
        docContent = documentation.content;
      }
    } catch (e) {
      docContent = { overview: documentation.content };
    }
    
    documentationContext = `
=== REPOSITORY DOCUMENTATION ===

${docContent.overview ? `## System Overview\n${docContent.overview}\n` : ""}

${docContent.components && docContent.components.length > 0 ? `## Existing Components\n${docContent.components.map((c: any) => `- ${c.name}: ${c.description}`).join("\n")}\n` : ""}

${docContent.apiServices && docContent.apiServices.length > 0 ? `## API Endpoints\n${docContent.apiServices.map((a: any) => `- ${a.name}: ${a.description}${a.endpoint ? ` [${a.method || 'GET'} ${a.endpoint}]` : ""}`).join("\n")}\n` : ""}

${docContent.dataModels && docContent.dataModels.length > 0 ? `## Data Models\n${docContent.dataModels.map((d: any) => `- ${d.name}: ${d.description}`).join("\n")}\n` : ""}

${docContent.features && docContent.features.length > 0 ? `## Existing Features\n${docContent.features.map((f: any) => `- ${f.name}: ${f.description}`).join("\n")}\n` : ""}

=== END DOCUMENTATION ===
`;
  }

  // Build database schema context if available
  let databaseSchemaContext = "";
  if (databaseSchema) {
    const tableDescriptions = databaseSchema.tables.map(table => {
      const columns = table.columns.map(col => {
        let desc = `    - ${col.name}: ${col.dataType}`;
        if (col.isPrimaryKey) desc += " (PK)";
        if (col.isForeignKey) desc += ` (FK -> ${col.references || "?"})`;
        if (!col.isNullable) desc += " NOT NULL";
        return desc;
      }).join("\n");
      return `  ${table.name} (${table.rowCount?.toLocaleString() || 0} rows):\n${columns}`;
    }).join("\n\n");
    
    databaseSchemaContext = `
=== DATABASE SCHEMA ===
Database: ${databaseSchema.databaseName}
Tables: ${databaseSchema.tables.length}

${tableDescriptions}
=== END DATABASE SCHEMA ===
`;
  }

  // Get project prefix from BRD title (first 3-4 chars uppercase)
  const projectPrefix = brd.title.split(/\s+/)[0]?.substring(0, 4).toUpperCase() || "PROJ";

  const systemPrompt = `You are a senior product manager creating JIRA-style user stories from a Business Requirements Document (BRD).

Create well-structured user stories that:
1. Follow the format: "As a [user type], I want [feature], so that [benefit]"
2. Include clear, testable acceptance criteria
3. Have appropriate story point estimates (1, 2, 3, 5, 8, 13)
4. Include relevant labels based on the feature area
5. Reference the documentation to ensure stories align with existing system architecture
6. Group related stories under appropriate epics
${databaseSchema ? `7. Reference specific database tables and columns when the story involves data changes
8. Include database-related acceptance criteria (e.g., data validation, constraints)

CRITICAL DATABASE REQUIREMENT:
If the BRD requirements involve ANY data storage, new entities, data models, or modifications to existing data structures, you MUST include at least one dedicated "Database Schema" user story that covers:
- Creating new tables or modifying existing tables
- Adding/modifying columns, constraints, indexes
- Setting up foreign key relationships
- Data migration if applicable
This database story should be one of the first stories (high priority) since other features depend on it.
Label it with "database" and include specific table/column names in the acceptance criteria.` : ""}

Use the following story key format: ${projectPrefix}-XXX (e.g., ${projectPrefix}-001, ${projectPrefix}-002)

Return a JSON object with this structure:
{
  "userStories": [
    {
      "storyKey": "${projectPrefix}-001",
      "title": "Brief story title",
      "description": "Detailed description of what needs to be built",
      "asA": "type of user",
      "iWant": "what the user wants to do",
      "soThat": "the benefit they get",
      "acceptanceCriteria": ["Given X, When Y, Then Z", ...],
      "priority": "highest|high|medium|low|lowest",
      "storyPoints": 3,
      "labels": ["frontend", "api", "database", etc.],
      "epic": "Name of the epic this belongs to",
      "relatedRequirementId": "FR-001",
      "technicalNotes": "Any technical implementation notes based on the documentation",
      "dependencies": ["${projectPrefix}-002", "External API setup", etc.]
    }
  ]
}`;

  const userPrompt = `Generate JIRA-style user stories for this BRD based on the repository documentation${databaseSchema ? ", database schema" : ""}${knowledgeContext ? ", and knowledge base documents" : ""}:

${documentationContext}
${databaseSchemaContext}
${knowledgeBaseContext}
${parentContext ? `=== PARENT STORY CONTEXT ===
These user stories will be created as subtasks of an existing JIRA story. Use this context to ensure the subtasks are aligned with and complement the parent story:

${parentContext}

Generate subtasks that break down the parent story's work into specific, actionable items.
=== END PARENT CONTEXT ===

` : ""}=== BUSINESS REQUIREMENTS DOCUMENT ===

Title: ${brd.title}
Version: ${brd.version}

Overview:
${brd.content.overview}

Objectives:
${brd.content.objectives.map((o, i) => `${i + 1}. ${o}`).join("\n")}

Scope:
- In Scope: ${brd.content.scope.inScope.join(", ")}
- Out of Scope: ${brd.content.scope.outOfScope.join(", ")}

Functional Requirements:
${JSON.stringify(brd.content.functionalRequirements, null, 2)}

Non-Functional Requirements:
${JSON.stringify(brd.content.nonFunctionalRequirements, null, 2)}

Technical Considerations:
${brd.content.technicalConsiderations.join("\n")}

Dependencies:
${brd.content.dependencies.join(", ")}

${brd.content.existingSystemContext ? `
Existing System Context:
- Relevant Components: ${brd.content.existingSystemContext.relevantComponents?.join(", ") || "None"}
- Relevant APIs: ${brd.content.existingSystemContext.relevantAPIs?.join(", ") || "None"}
- Data Models Affected: ${brd.content.existingSystemContext.dataModelsAffected?.join(", ") || "None"}
` : ""}

IMPORTANT: 
1. Create user stories that reference actual components and APIs from the documentation
2. Include technical notes that guide developers on how to integrate with existing code
3. Ensure acceptance criteria are specific and testable
4. Group related stories under logical epics${parentContext ? "\n5. Since these will be subtasks, make them more granular and specific to support the parent story" : ""}`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const content = await callPwcGenAI(prompt);
  const data = parseJsonResponse(content);
  
  return data.userStories.map((story: any, index: number) => ({
    brdId: brd.id,
    storyKey: story.storyKey || `${projectPrefix}-${String(index + 1).padStart(3, "0")}`,
    title: story.title,
    description: story.description,
    asA: story.asA,
    iWant: story.iWant,
    soThat: story.soThat,
    acceptanceCriteria: story.acceptanceCriteria || [],
    priority: story.priority || "medium",
    storyPoints: story.storyPoints || null,
    labels: story.labels || [],
    epic: story.epic || null,
    relatedRequirementId: story.relatedRequirementId || null,
    technicalNotes: story.technicalNotes || null,
    dependencies: story.dependencies || [],
  }));
}

// Generate VS Code Copilot prompt for implementing features
export async function generateCopilotPrompt(
  userStories: UserStory[],
  documentation: Documentation | null,
  analysis: RepoAnalysis | null,
  databaseSchema: DatabaseSchemaInfo | null
): Promise<string> {
  // Build folder structure from analysis features and architecture
  const folderStructure = analysis
    ? analysis.features
        .flatMap((f: any) => f.files || [])
        .slice(0, 50)
        .join("\n")
    : "Not available";

  // Format user stories
  const storiesText = userStories.map(story => `
### ${story.storyKey}: ${story.title}
**User Story:** As a ${story.asA}, I want ${story.iWant}, so that ${story.soThat}
**Priority:** ${story.priority} | **Story Points:** ${story.storyPoints || "N/A"}
**Acceptance Criteria:**
${story.acceptanceCriteria.map(c => `- ${c}`).join("\n")}
${story.technicalNotes ? `**Technical Notes:** ${story.technicalNotes}` : ""}
${story.dependencies.length > 0 ? `**Dependencies:** ${story.dependencies.join(", ")}` : ""}
`).join("\n");

  // Format documentation context (content is a string, sections have title/content)
  const docsContext = documentation ? `
## Existing Documentation

${documentation.content}

${documentation.sections.map((s: any) => `### ${s.title}\n${s.content}`).join("\n\n")}
` : "";

  // Format database schema context
  let dbSchemaContext = "";
  if (databaseSchema) {
    const tableDescriptions = databaseSchema.tables.map(table => {
      const columns = table.columns.map(col => {
        let desc = `  - ${col.name}: ${col.dataType}`;
        if (col.isPrimaryKey) desc += " (PRIMARY KEY)";
        if (col.isForeignKey) desc += ` (FOREIGN KEY -> ${col.references || "?"})`;
        if (!col.isNullable) desc += " NOT NULL";
        return desc;
      }).join("\n");
      return `### ${table.name} (${table.rowCount?.toLocaleString() || 0} rows)\n${columns}`;
    }).join("\n\n");
    
    dbSchemaContext = `
## Database Schema (${databaseSchema.databaseName})

${tableDescriptions}
`;
  }

  const systemPrompt = `You are an expert at creating detailed implementation prompts for VS Code Copilot agents.
Your task is to generate a comprehensive, actionable prompt that a developer can use with GitHub Copilot
to implement the requested features.

The prompt should:
1. Clearly describe what needs to be built
2. Reference the existing codebase architecture and folder structure
3. Specify which files to create or modify
4. Include code patterns to follow based on existing code
5. List step-by-step implementation instructions
6. Include testing requirements
7. Be formatted for easy copy-paste into VS Code Copilot chat
${databaseSchema ? "8. Include database schema details for any data-related implementation" : ""}`;

  const userPrompt = `Generate a VS Code Copilot implementation prompt based on the following context:

## User Stories to Implement
${storiesText}

${docsContext}

## Project Architecture & Tech Stack
${analysis ? `
Languages: ${analysis.techStack.languages.join(", ")}
Frameworks: ${analysis.techStack.frameworks.join(", ")}
Tools: ${analysis.techStack.tools.join(", ")}
` : "Not available"}

## Folder Structure
\`\`\`
${folderStructure}
\`\`\`
${dbSchemaContext}
Generate a comprehensive Copilot prompt that:
1. Starts with a clear objective
2. Lists the user stories to implement
3. Describes the existing architecture to work within
4. Specifies files to create/modify with their paths
5. Provides step-by-step implementation guide
6. Includes code patterns and conventions to follow
7. Lists acceptance criteria as checkboxes
8. Adds testing requirements

Format the output as a ready-to-use Copilot prompt that can be pasted directly into VS Code.`;

  const prompt = buildPrompt(systemPrompt, userPrompt);
  const response = await callPwcGenAI(prompt);

  return response || "Failed to generate prompt";
}

// Semantic search to find related JIRA stories
export interface JiraStoryForSearch {
  key: string;
  summary: string;
  description: string;
  status: string;
  priority: string;
  labels: string[];
}

export interface RelatedStoryResult {
  story: JiraStoryForSearch;
  relevanceScore: number;
  reason: string;
}

export async function findRelatedStories(
  featureDescription: string,
  jiraStories: JiraStoryForSearch[]
): Promise<RelatedStoryResult[]> {
  if (jiraStories.length === 0) {
    return [];
  }

  const storiesContext = jiraStories.map((story, i) => 
    `${i + 1}. [${story.key}] ${story.summary}\n   Description: ${story.description?.slice(0, 200) || "N/A"}...`
  ).join("\n\n");

  const systemPrompt = `You are an expert at analyzing user stories and feature requirements to find semantic relationships.
Your task is to identify existing JIRA stories that are related to a new feature request.

Consider stories related if they:
- Address similar functionality or user needs
- Work on the same area of the application
- Have overlapping acceptance criteria or goals
- Could serve as a parent story for subtasks

Return a JSON array of related stories with relevance scores (0-100) and reasons.
Only include stories with relevance score >= 60.
Return at most 5 related stories, sorted by relevance.

Response format:
{
  "relatedStories": [
    {
      "storyKey": "KAN-123",
      "relevanceScore": 85,
      "reason": "Brief explanation of why this story is related"
    }
  ]
}`;

  const userPrompt = `## New Feature Request:
${featureDescription}

## Existing JIRA Stories:
${storiesContext}

Analyze the feature request and find which existing stories are semantically related. Return empty array if no strong matches found.`;

  try {
    const prompt = buildPrompt(systemPrompt, userPrompt);
    const responseText = await callPwcGenAI(prompt);
    const result = parseJsonResponse(responseText);
    
    const relatedStories: RelatedStoryResult[] = (result.relatedStories || [])
      .map((match: any) => {
        const story = jiraStories.find(s => s.key === match.storyKey);
        if (!story) return null;
        return {
          story,
          relevanceScore: match.relevanceScore,
          reason: match.reason
        };
      })
      .filter((s: RelatedStoryResult | null): s is RelatedStoryResult => s !== null)
      .sort((a: RelatedStoryResult, b: RelatedStoryResult) => b.relevanceScore - a.relevanceScore);
    
    return relatedStories;
  } catch (error) {
    console.error("Error parsing related stories response:", error);
    return [];
  }
}
