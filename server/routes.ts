import type { Express, Request, Response } from "express";
import { createServer, type Server } from "http";
import multer from "multer";
import { z } from "zod";
import { Client } from "pg";
import { storage } from "./storage";
import { analyzeRepository, generateDocumentation, generateBPMNDiagram, generateBRD, generateTestCases, generateTestData, generateUserStories, generateCopilotPrompt, transcribeAudio } from "./ai";
import type { DatabaseTable, DatabaseColumn } from "@shared/schema";

const upload = multer({ storage: multer.memoryStorage() });

const analyzeRequestSchema = z.object({
  repoUrl: z.string().url().regex(/github\.com\/[\w-]+\/[\w.-]+/)
});

const requirementsSchema = z.object({
  title: z.string().min(1),
  description: z.string().optional(),
  inputType: z.enum(["text", "file", "audio"])
});

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  
  // Projects
  app.get("/api/projects", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      res.json(projects);
    } catch (error) {
      console.error("Error fetching projects:", error);
      res.status(500).json({ error: "Failed to fetch projects" });
    }
  });

  app.get("/api/projects/:id", async (req: Request, res: Response) => {
    try {
      const id = req.params.id as string;
      const project = await storage.getProject(id);
      if (!project) {
        return res.status(404).json({ error: "Project not found" });
      }
      res.json(project);
    } catch (error) {
      console.error("Error fetching project:", error);
      res.status(500).json({ error: "Failed to fetch project" });
    }
  });

  // Analyze Repository
  app.post("/api/projects/analyze", async (req: Request, res: Response) => {
    try {
      const parseResult = analyzeRequestSchema.safeParse(req.body);
      if (!parseResult.success) {
        return res.status(400).json({ error: "Invalid request: " + parseResult.error.message });
      }
      
      const { repoUrl } = parseResult.data;

      // Extract repo name from URL
      const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
      if (!match) {
        return res.status(400).json({ error: "Invalid GitHub URL" });
      }

      const repoName = `${match[1]}/${match[2]}`.replace(/\.git$/, "");

      // Create project with pending status
      const project = await storage.createProject({
        name: repoName,
        repoUrl,
        techStack: [],
        status: "analyzing",
      });

      // Analyze repository asynchronously and persist results
      analyzeRepository(repoUrl, project.id)
        .then(async (analysis) => {
          try {
            // Persist the analysis
            await storage.createAnalysis(analysis);
            
            // Update project with tech stack first
            await storage.updateProject(project.id, {
              techStack: [
                ...analysis.techStack.languages,
                ...analysis.techStack.frameworks,
              ],
              description: analysis.summary,
            });
            
            // Generate and persist documentation (non-blocking on failure)
            try {
              const updatedProject = await storage.getProject(project.id);
              if (updatedProject) {
                const documentation = await generateDocumentation(analysis, updatedProject);
                const savedDoc = await storage.createDocumentation(documentation);
                
                // Generate BPMN diagrams after documentation is created
                try {
                  console.log("Generating BPMN diagrams for features...");
                  const bpmnData = await generateBPMNDiagram(savedDoc, analysis);
                  await storage.createBPMNDiagram(bpmnData);
                  console.log("BPMN diagrams generated successfully");
                } catch (bpmnError) {
                  console.error("BPMN diagram generation error:", bpmnError);
                  // Continue - documentation succeeded, just BPMN failed
                }
              }
            } catch (docError) {
              console.error("Documentation generation error:", docError);
              // Continue - analysis succeeded, just docs failed
            }
            
            // Mark as completed
            await storage.updateProject(project.id, { status: "completed" });
          } catch (persistError) {
            console.error("Error persisting analysis:", persistError);
            await storage.updateProject(project.id, { status: "error" });
          }
        })
        .catch(async (error) => {
          console.error("Analysis error:", error);
          await storage.updateProject(project.id, { status: "error" });
        });

      res.status(201).json(project);
    } catch (error) {
      console.error("Error analyzing repository:", error);
      res.status(500).json({ error: "Failed to analyze repository" });
    }
  });

  // Get current analysis
  app.get("/api/analysis/current", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(404).json({ error: "No projects found" });
      }
      const analysis = await storage.getAnalysis(projects[0].id);
      if (!analysis) {
        return res.status(404).json({ error: "No analysis found" });
      }
      res.json(analysis);
    } catch (error) {
      console.error("Error fetching analysis:", error);
      res.status(500).json({ error: "Failed to fetch analysis" });
    }
  });

  // Get current documentation
  app.get("/api/documentation/current", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(404).json({ error: "No projects found" });
      }
      const doc = await storage.getDocumentation(projects[0].id);
      if (!doc) {
        return res.status(404).json({ error: "No documentation found" });
      }
      res.json(doc);
    } catch (error) {
      console.error("Error fetching documentation:", error);
      res.status(500).json({ error: "Failed to fetch documentation" });
    }
  });

  // Get BPMN diagrams for current documentation
  app.get("/api/bpmn/current", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(404).json({ error: "No projects found" });
      }
      const doc = await storage.getDocumentation(projects[0].id);
      if (!doc) {
        return res.status(404).json({ error: "No documentation found" });
      }
      const bpmn = await storage.getBPMNDiagram(doc.id);
      if (!bpmn) {
        return res.status(404).json({ error: "No BPMN diagrams found" });
      }
      res.json(bpmn);
    } catch (error) {
      console.error("Error fetching BPMN diagrams:", error);
      res.status(500).json({ error: "Failed to fetch BPMN diagrams" });
    }
  });

  // Regenerate BPMN diagram using existing documentation
  app.post("/api/bpmn/regenerate", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(404).json({ error: "No projects found" });
      }
      const project = projects[0];
      const doc = await storage.getDocumentation(project.id);
      if (!doc) {
        return res.status(404).json({ error: "No documentation found" });
      }
      const analysis = await storage.getAnalysis(project.id);
      if (!analysis) {
        return res.status(404).json({ error: "No analysis found" });
      }

      // Delete existing BPMN diagram if any
      await storage.deleteBPMNDiagram(doc.id);

      // Generate new BPMN diagram
      const bpmnData = await generateBPMNDiagram(doc, analysis);
      const newBpmn = await storage.createBPMNDiagram(bpmnData);
      
      res.json(newBpmn);
    } catch (error) {
      console.error("Error regenerating BPMN diagram:", error);
      res.status(500).json({ error: "Failed to regenerate BPMN diagram" });
    }
  });

  // Database Schema - Connect and fetch schema from external PostgreSQL
  app.post("/api/database-schema/connect", async (req: Request, res: Response) => {
    try {
      const { connectionString } = req.body;
      
      if (!connectionString || typeof connectionString !== "string") {
        return res.status(400).json({ error: "Connection string is required" });
      }

      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(400).json({ error: "Please analyze a repository first" });
      }
      const project = projects[0];

      // Connect to external PostgreSQL
      const client = new Client({ connectionString });
      
      try {
        await client.connect();
        
        // Get database name
        const dbNameResult = await client.query("SELECT current_database()");
        const databaseName = dbNameResult.rows[0].current_database;

        // Get all tables with their columns
        const tablesQuery = `
          SELECT 
            t.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
            CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_foreign_key,
            fk.foreign_table_name || '.' || fk.foreign_column_name as references_column
          FROM information_schema.tables t
          JOIN information_schema.columns c ON t.table_name = c.table_name AND t.table_schema = c.table_schema
          LEFT JOIN (
            SELECT ku.table_name, ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
          ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
          LEFT JOIN (
            SELECT 
              kcu.table_name,
              kcu.column_name,
              ccu.table_name AS foreign_table_name,
              ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
          ) fk ON c.table_name = fk.table_name AND c.column_name = fk.column_name
          WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
          ORDER BY t.table_name, c.ordinal_position
        `;

        const result = await client.query(tablesQuery);
        
        // Group by table
        const tablesMap = new Map<string, DatabaseColumn[]>();
        for (const row of result.rows) {
          if (!tablesMap.has(row.table_name)) {
            tablesMap.set(row.table_name, []);
          }
          tablesMap.get(row.table_name)!.push({
            name: row.column_name,
            dataType: row.data_type,
            isNullable: row.is_nullable === "YES",
            defaultValue: row.column_default,
            isPrimaryKey: row.is_primary_key,
            isForeignKey: row.is_foreign_key,
            references: row.references_column,
          });
        }

        // Convert to array of tables
        const tables: DatabaseTable[] = [];
        for (const [tableName, columns] of tablesMap.entries()) {
          // Get row count for each table
          const countResult = await client.query(`SELECT COUNT(*) FROM "${tableName}"`);
          tables.push({
            name: tableName,
            columns,
            rowCount: parseInt(countResult.rows[0].count, 10),
          });
        }

        await client.end();

        // Delete existing schema if any
        await storage.deleteDatabaseSchema(project.id);

        // Store the schema (mask the password in stored connection string)
        const maskedConnectionString = connectionString.replace(
          /(:\/\/[^:]+:)[^@]+(@)/,
          "$1****$2"
        );

        const schemaInfo = await storage.createDatabaseSchema({
          projectId: project.id,
          connectionString: maskedConnectionString,
          databaseName,
          tables,
        });

        res.json(schemaInfo);
      } catch (dbError: any) {
        await client.end().catch(() => {});
        console.error("Database connection error:", dbError);
        res.status(400).json({ 
          error: "Failed to connect to database", 
          details: dbError.message 
        });
      }
    } catch (error) {
      console.error("Error processing database schema:", error);
      res.status(500).json({ error: "Failed to process database schema" });
    }
  });

  // Get current database schema
  app.get("/api/database-schema/current", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.json(null);
      }
      const project = projects[0];
      const schema = await storage.getDatabaseSchema(project.id);
      res.json(schema || null);
    } catch (error) {
      console.error("Error fetching database schema:", error);
      res.status(500).json({ error: "Failed to fetch database schema" });
    }
  });

  // Delete database schema
  app.delete("/api/database-schema/current", async (req: Request, res: Response) => {
    try {
      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(404).json({ error: "No project found" });
      }
      const project = projects[0];
      await storage.deleteDatabaseSchema(project.id);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting database schema:", error);
      res.status(500).json({ error: "Failed to delete database schema" });
    }
  });

  // Feature Requirements
  app.post("/api/requirements", upload.fields([
    { name: "file", maxCount: 1 },
    { name: "audio", maxCount: 1 }
  ]), async (req: Request, res: Response) => {
    try {
      const parseResult = requirementsSchema.safeParse(req.body);
      if (!parseResult.success) {
        return res.status(400).json({ error: "Invalid request: title is required" });
      }
      
      const { title, description, inputType } = parseResult.data;
      const files = req.files as { [fieldname: string]: Express.Multer.File[] } | undefined;

      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(400).json({ error: "Please analyze a repository first" });
      }

      let finalDescription = description || "";

      // Handle audio transcription
      if (inputType === "audio" && files?.audio?.[0]) {
        const audioBuffer = files.audio[0].buffer;
        finalDescription = await transcribeAudio(audioBuffer);
      }

      // Handle file upload
      if (inputType === "file" && files?.file?.[0]) {
        finalDescription = files.file[0].buffer.toString("utf-8");
      }

      const featureRequest = await storage.createFeatureRequest({
        projectId: projects[0].id,
        title,
        description: finalDescription,
        inputType,
        rawInput: finalDescription,
      });

      res.status(201).json(featureRequest);
    } catch (error) {
      console.error("Error creating feature request:", error);
      res.status(500).json({ error: "Failed to create feature request" });
    }
  });

  // Get current BRD
  app.get("/api/brd/current", async (req: Request, res: Response) => {
    try {
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(404).json({ error: "No BRD found" });
      }
      res.json(brd);
    } catch (error) {
      console.error("Error fetching BRD:", error);
      res.status(500).json({ error: "Failed to fetch BRD" });
    }
  });

  // Generate BRD with streaming
  app.post("/api/brd/generate", async (req: Request, res: Response) => {
    try {
      const featureRequest = await storage.getCurrentFeatureRequest();
      if (!featureRequest) {
        return res.status(400).json({ error: "No feature request found" });
      }

      const projects = await storage.getAllProjects();
      if (projects.length === 0) {
        return res.status(400).json({ error: "No project found" });
      }

      const analysis = await storage.getAnalysis(projects[0].id);
      const documentation = await storage.getDocumentation(projects[0].id);

      // Set up SSE with proper headers
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      res.setHeader("X-Accel-Buffering", "no");
      res.flushHeaders();

      // Handle client disconnect
      let isClientConnected = true;
      req.on("close", () => {
        isClientConnected = false;
      });

      // Send keep-alive
      const keepAlive = setInterval(() => {
        if (isClientConnected) {
          res.write(": keep-alive\n\n");
        }
      }, 15000);

      try {
        // Generate BRD using documentation as context
        const brd = await generateBRD(
          featureRequest,
          analysis || null,
          documentation || null,
          (chunk) => {
            if (isClientConnected) {
              res.write(`data: ${JSON.stringify({ content: chunk })}\n\n`);
            }
          }
        );

        await storage.createBRD(brd);

        if (isClientConnected) {
          res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
        }
      } catch (genError) {
        console.error("BRD generation error:", genError);
        if (isClientConnected) {
          res.write(`data: ${JSON.stringify({ error: "Generation failed" })}\n\n`);
        }
      } finally {
        clearInterval(keepAlive);
        res.end();
      }
    } catch (error) {
      console.error("Error generating BRD:", error);
      if (!res.headersSent) {
        res.status(500).json({ error: "Failed to generate BRD" });
      } else {
        res.write(`data: ${JSON.stringify({ error: "Generation failed" })}\n\n`);
        res.end();
      }
    }
  });

  // Get test cases
  app.get("/api/test-cases", async (req: Request, res: Response) => {
    try {
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.json([]);
      }
      const testCases = await storage.getTestCases(brd.id);
      res.json(testCases);
    } catch (error) {
      console.error("Error fetching test cases:", error);
      res.status(500).json({ error: "Failed to fetch test cases" });
    }
  });

  // Generate test cases
  app.post("/api/test-cases/generate", async (req: Request, res: Response) => {
    try {
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found. Please generate a BRD first." });
      }

      const projects = await storage.getAllProjects();
      const analysis = projects.length > 0 ? await storage.getAnalysis(projects[0].id) : null;
      const documentation = projects.length > 0 ? await storage.getDocumentation(projects[0].id) : null;

      const testCases = await generateTestCases(brd, analysis || null, documentation || null);
      if (!testCases || testCases.length === 0) {
        return res.status(500).json({ error: "Failed to generate test cases - no cases returned" });
      }
      
      const savedTestCases = await storage.createTestCases(testCases);
      res.json(savedTestCases);
    } catch (error) {
      console.error("Error generating test cases:", error);
      res.status(500).json({ error: "Failed to generate test cases" });
    }
  });

  // Get test data
  app.get("/api/test-data", async (req: Request, res: Response) => {
    try {
      const testData = await storage.getAllTestData();
      res.json(testData);
    } catch (error) {
      console.error("Error fetching test data:", error);
      res.status(500).json({ error: "Failed to fetch test data" });
    }
  });

  // Generate test data
  app.post("/api/test-data/generate", async (req: Request, res: Response) => {
    try {
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found. Please generate a BRD first." });
      }

      const testCases = await storage.getTestCases(brd.id);
      if (testCases.length === 0) {
        return res.status(400).json({ error: "No test cases found. Please generate test cases first." });
      }

      const projects = await storage.getAllProjects();
      const documentation = projects.length > 0 ? await storage.getDocumentation(projects[0].id) : null;

      const testData = await generateTestData(testCases, brd, documentation || null);
      if (!testData || testData.length === 0) {
        return res.status(500).json({ error: "Failed to generate test data - no data returned" });
      }
      
      const savedTestData = await storage.createTestDataBatch(testData);
      res.json(savedTestData);
    } catch (error) {
      console.error("Error generating test data:", error);
      res.status(500).json({ error: "Failed to generate test data" });
    }
  });

  // Get user stories for a BRD
  app.get("/api/user-stories/:brdId", async (req: Request, res: Response) => {
    try {
      const userStories = await storage.getUserStories(req.params.brdId as string);
      res.json(userStories);
    } catch (error) {
      console.error("Error fetching user stories:", error);
      res.status(500).json({ error: "Failed to fetch user stories" });
    }
  });

  // Generate user stories from BRD
  app.post("/api/user-stories/generate", async (req: Request, res: Response) => {
    try {
      const { parentJiraKey } = req.body || {};
      
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found. Please generate a BRD first." });
      }

      const projects = await storage.getAllProjects();
      const documentation = projects.length > 0 ? await storage.getDocumentation(projects[0].id) : null;

      // If there's a parent JIRA key, fetch its content for context
      let parentContext: string | null = null;
      if (parentJiraKey) {
        try {
          const jiraEmail = process.env.JIRA_EMAIL;
          const jiraToken = process.env.JIRA_API_TOKEN;
          const jiraInstanceUrl = process.env.JIRA_INSTANCE_URL || "daspapun21.atlassian.net";
          
          if (jiraEmail && jiraToken) {
            const auth = Buffer.from(`${jiraEmail}:${jiraToken}`).toString('base64');
            const response = await fetch(
              `https://${jiraInstanceUrl}/rest/api/3/issue/${parentJiraKey}?fields=summary,description`,
              {
                headers: {
                  'Authorization': `Basic ${auth}`,
                  'Accept': 'application/json'
                }
              }
            );
            if (response.ok) {
              const issue = await response.json();
              // Extract text from ADF description
              const descriptionText = extractTextFromADF(issue.fields.description);
              parentContext = `Parent Story [${parentJiraKey}]: ${issue.fields.summary}${descriptionText ? `\n\nDescription: ${descriptionText}` : ""}`;
            }
          }
        } catch (err) {
          console.error("Error fetching parent JIRA story:", err);
        }
      }

      const userStories = await generateUserStories(brd, documentation || null, parentContext);
      if (!userStories || userStories.length === 0) {
        return res.status(500).json({ error: "Failed to generate user stories - no stories returned" });
      }
      
      // Set parentJiraKey on all stories if provided
      const storiesWithParent = userStories.map(story => ({
        ...story,
        parentJiraKey: parentJiraKey || null
      }));
      
      const savedStories = await storage.createUserStories(storiesWithParent);
      res.json(savedStories);
    } catch (error) {
      console.error("Error generating user stories:", error);
      res.status(500).json({ error: "Failed to generate user stories" });
    }
  });

  // Update a user story
  app.patch("/api/user-stories/:id", async (req: Request, res: Response) => {
    try {
      const id = req.params.id as string;
      const updates = req.body;
      const updatedStory = await storage.updateUserStory(id, updates);
      if (!updatedStory) {
        return res.status(404).json({ error: "User story not found" });
      }
      res.json(updatedStory);
    } catch (error) {
      console.error("Error updating user story:", error);
      res.status(500).json({ error: "Failed to update user story" });
    }
  });

  app.delete("/api/user-stories/:id", async (req: Request, res: Response) => {
    try {
      const id = req.params.id as string;
      const deleted = await storage.deleteUserStory(id);
      if (!deleted) {
        return res.status(404).json({ error: "User story not found" });
      }
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting user story:", error);
      res.status(500).json({ error: "Failed to delete user story" });
    }
  });

  // Generate Copilot prompt from user stories
  app.post("/api/copilot-prompt/generate", async (req: Request, res: Response) => {
    try {
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found. Please generate a BRD first." });
      }

      const userStories = await storage.getUserStories(brd.id);
      if (!userStories || userStories.length === 0) {
        return res.status(400).json({ error: "No user stories found. Please generate user stories first." });
      }

      const projects = await storage.getAllProjects();
      const documentation = projects.length > 0 ? await storage.getDocumentation(projects[0].id) : null;
      const analysis = projects.length > 0 ? await storage.getAnalysis(projects[0].id) : null;

      const prompt = await generateCopilotPrompt(userStories, documentation || null, analysis || null);
      res.json({ prompt });
    } catch (error) {
      console.error("Error generating Copilot prompt:", error);
      res.status(500).json({ error: "Failed to generate Copilot prompt" });
    }
  });

  // Sync user stories to JIRA
  app.post("/api/jira/sync", async (req: Request, res: Response) => {
    try {
      const jiraEmail = process.env.JIRA_EMAIL;
      const jiraToken = process.env.JIRA_API_TOKEN;
      const jiraInstanceUrl = process.env.JIRA_INSTANCE_URL || "daspapun21.atlassian.net";
      const jiraProjectKey = process.env.JIRA_PROJECT_KEY || "KAN";

      if (!jiraEmail || !jiraToken) {
        return res.status(400).json({ 
          error: "JIRA credentials not configured. Please add JIRA_EMAIL and JIRA_API_TOKEN secrets." 
        });
      }

      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found. Please generate a BRD first." });
      }

      const userStories = await storage.getUserStories(brd.id);
      if (!userStories || userStories.length === 0) {
        return res.status(400).json({ error: "No user stories found. Please generate user stories first." });
      }

      const auth = Buffer.from(`${jiraEmail}:${jiraToken}`).toString('base64');
      const jiraBaseUrl = `https://${jiraInstanceUrl}/rest/api/3`;
      
      const results: { storyKey: string; jiraKey?: string; error?: string }[] = [];

      for (const story of userStories) {
        try {
          const description = {
            type: "doc",
            version: 1,
            content: [
              {
                type: "paragraph",
                content: [
                  { type: "text", text: `As a ${story.asA}, I want ${story.iWant}, so that ${story.soThat}` }
                ]
              },
              ...(story.description ? [{
                type: "paragraph",
                content: [{ type: "text", text: story.description }]
              }] : []),
              {
                type: "heading",
                attrs: { level: 3 },
                content: [{ type: "text", text: "Acceptance Criteria" }]
              },
              {
                type: "bulletList",
                content: story.acceptanceCriteria.map(criteria => ({
                  type: "listItem",
                  content: [{
                    type: "paragraph",
                    content: [{ type: "text", text: criteria }]
                  }]
                }))
              },
              ...(story.technicalNotes ? [
                {
                  type: "heading",
                  attrs: { level: 3 },
                  content: [{ type: "text", text: "Technical Notes" }]
                },
                {
                  type: "paragraph",
                  content: [{ type: "text", text: story.technicalNotes }]
                }
              ] : [])
            ]
          };

          const priorityMap: Record<string, string> = {
            'highest': 'Highest',
            'high': 'High',
            'medium': 'Medium',
            'low': 'Low',
            'lowest': 'Lowest'
          };

          // Determine if this is a subtask or a regular story
          const isSubtask = !!story.parentJiraKey;
          
          const issueData: any = {
            fields: {
              project: { key: jiraProjectKey },
              summary: story.title,
              description: description,
              issuetype: { name: isSubtask ? "Subtask" : "Story" },
              labels: story.labels || []
            }
          };

          // Add parent reference for subtasks
          if (isSubtask && story.parentJiraKey) {
            issueData.fields.parent = { key: story.parentJiraKey };
          }

          const response = await fetch(`${jiraBaseUrl}/issue`, {
            method: 'POST',
            headers: {
              'Authorization': `Basic ${auth}`,
              'Accept': 'application/json',
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(issueData)
          });

          if (response.ok) {
            const data = await response.json();
            const resultInfo: any = { storyKey: story.storyKey, jiraKey: data.key };
            if (isSubtask) {
              resultInfo.parentKey = story.parentJiraKey;
              resultInfo.isSubtask = true;
            }
            results.push(resultInfo);
          } else {
            const errorData = await response.text();
            console.error(`JIRA API error for ${story.storyKey}:`, errorData);
            results.push({ storyKey: story.storyKey, error: `Failed to create issue: ${response.status}` });
          }
        } catch (err) {
          console.error(`Error syncing story ${story.storyKey}:`, err);
          results.push({ storyKey: story.storyKey, error: String(err) });
        }
      }

      const successCount = results.filter(r => r.jiraKey).length;
      const failCount = results.filter(r => r.error).length;

      res.json({ 
        message: `Synced ${successCount} stories to JIRA. ${failCount > 0 ? `${failCount} failed.` : ''}`,
        results 
      });
    } catch (error) {
      console.error("Error syncing to JIRA:", error);
      res.status(500).json({ error: "Failed to sync to JIRA" });
    }
  });

  // Fetch all stories from JIRA board
  app.get("/api/jira/stories", async (req: Request, res: Response) => {
    try {
      const jiraEmail = process.env.JIRA_EMAIL;
      const jiraToken = process.env.JIRA_API_TOKEN;
      const jiraInstanceUrl = process.env.JIRA_INSTANCE_URL || "daspapun21.atlassian.net";
      const jiraProjectKey = process.env.JIRA_PROJECT_KEY || "KAN";

      if (!jiraEmail || !jiraToken) {
        return res.status(400).json({ 
          error: "JIRA credentials not configured. Please add JIRA_EMAIL and JIRA_API_TOKEN secrets." 
        });
      }

      const auth = Buffer.from(`${jiraEmail}:${jiraToken}`).toString('base64');
      const jiraBaseUrl = `https://${jiraInstanceUrl}/rest/api/3`;
      
      // Fetch all stories from the project using new JIRA search API
      const jql = encodeURIComponent(`project = ${jiraProjectKey} AND issuetype = Story ORDER BY created DESC`);
      const response = await fetch(
        `${jiraBaseUrl}/search/jql?jql=${jql}&fields=summary,description,status,priority,labels,subtasks`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Basic ${auth}`,
            'Accept': 'application/json'
          }
        }
      );

      if (!response.ok) {
        const errorData = await response.text();
        console.error("JIRA API error:", errorData);
        return res.status(response.status).json({ error: "Failed to fetch JIRA stories" });
      }

      const data = await response.json();
      const stories = data.issues.map((issue: any) => ({
        key: issue.key,
        summary: issue.fields.summary,
        description: extractTextFromADF(issue.fields.description),
        status: issue.fields.status?.name || "Unknown",
        priority: issue.fields.priority?.name || "Medium",
        labels: issue.fields.labels || [],
        subtaskCount: issue.fields.subtasks?.length || 0
      }));

      res.json(stories);
    } catch (error) {
      console.error("Error fetching JIRA stories:", error);
      res.status(500).json({ error: "Failed to fetch JIRA stories" });
    }
  });

  // Find related JIRA stories using semantic search
  app.post("/api/jira/find-related", async (req: Request, res: Response) => {
    try {
      const { featureDescription } = req.body;
      if (!featureDescription) {
        return res.status(400).json({ error: "Feature description is required" });
      }

      const jiraEmail = process.env.JIRA_EMAIL;
      const jiraToken = process.env.JIRA_API_TOKEN;
      const jiraInstanceUrl = process.env.JIRA_INSTANCE_URL || "daspapun21.atlassian.net";
      const jiraProjectKey = process.env.JIRA_PROJECT_KEY || "KAN";

      console.log("JIRA find-related config:", { jiraEmail: jiraEmail ? "set" : "not set", jiraToken: jiraToken ? "set" : "not set", jiraInstanceUrl, jiraProjectKey });

      if (!jiraEmail || !jiraToken) {
        console.log("Missing JIRA credentials, returning empty");
        return res.status(200).json({ relatedStories: [] }); // Return empty if no JIRA config
      }

      const auth = Buffer.from(`${jiraEmail}:${jiraToken}`).toString('base64');
      const jiraBaseUrl = `https://${jiraInstanceUrl}/rest/api/3`;
      
      // Fetch all stories from the project using new JIRA search API
      const jql = encodeURIComponent(`project = ${jiraProjectKey} ORDER BY created DESC`);
      const fetchUrl = `${jiraBaseUrl}/search/jql?jql=${jql}&fields=summary,description,status,priority,labels,issuetype&maxResults=100`;
      console.log("Fetching JIRA stories:", fetchUrl);
      
      const response = await fetch(
        fetchUrl,
        {
          method: 'GET',
          headers: {
            'Authorization': `Basic ${auth}`,
            'Accept': 'application/json'
          }
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        console.error("JIRA API error:", response.status, errorText);
        return res.status(200).json({ relatedStories: [] });
      }

      const data = await response.json();
      console.log(`Found ${data.issues?.length || 0} JIRA issues`);
      
      const jiraStories = (data.issues || []).map((issue: any) => ({
        key: issue.key,
        summary: issue.fields.summary,
        description: extractTextFromADF(issue.fields.description),
        status: issue.fields.status?.name || "Unknown",
        priority: issue.fields.priority?.name || "Medium",
        labels: issue.fields.labels || [],
        issueType: issue.fields.issuetype?.name || "Unknown"
      }));

      console.log("Mapped JIRA stories:", jiraStories.map((s: any) => ({ key: s.key, summary: s.summary, issueType: s.issueType })));

      if (jiraStories.length === 0) {
        console.log("No JIRA stories found in project");
        return res.json({ relatedStories: [] });
      }

      // Use OpenAI to find semantically related stories
      console.log("Finding related stories using AI semantic search...");
      const { findRelatedStories } = await import("./ai");
      const relatedStories = await findRelatedStories(featureDescription, jiraStories);
      console.log(`AI found ${relatedStories.length} related stories`);
      
      res.json({ relatedStories });
    } catch (error) {
      console.error("Error finding related stories:", error);
      res.status(500).json({ error: "Failed to find related stories" });
    }
  });

  // Sync a single story as a subtask of a parent JIRA issue
  app.post("/api/jira/sync-subtask", async (req: Request, res: Response) => {
    try {
      const { storyId, parentKey } = req.body;
      
      if (!storyId || !parentKey) {
        return res.status(400).json({ error: "Story ID and parent JIRA key are required" });
      }

      const jiraEmail = process.env.JIRA_EMAIL;
      const jiraToken = process.env.JIRA_API_TOKEN;
      const jiraInstanceUrl = process.env.JIRA_INSTANCE_URL || "daspapun21.atlassian.net";
      const jiraProjectKey = process.env.JIRA_PROJECT_KEY || "KAN";

      if (!jiraEmail || !jiraToken) {
        return res.status(400).json({ 
          error: "JIRA credentials not configured. Please add JIRA_EMAIL and JIRA_API_TOKEN secrets." 
        });
      }

      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found" });
      }

      const userStories = await storage.getUserStories(brd.id);
      const story = userStories?.find(s => s.id === storyId);
      
      if (!story) {
        return res.status(404).json({ error: "User story not found" });
      }

      const auth = Buffer.from(`${jiraEmail}:${jiraToken}`).toString('base64');
      const jiraBaseUrl = `https://${jiraInstanceUrl}/rest/api/3`;

      const description = {
        type: "doc",
        version: 1,
        content: [
          {
            type: "paragraph",
            content: [
              { type: "text", text: `As a ${story.asA}, I want ${story.iWant}, so that ${story.soThat}` }
            ]
          },
          ...(story.description ? [{
            type: "paragraph",
            content: [{ type: "text", text: story.description }]
          }] : []),
          {
            type: "heading",
            attrs: { level: 3 },
            content: [{ type: "text", text: "Acceptance Criteria" }]
          },
          {
            type: "bulletList",
            content: story.acceptanceCriteria.map(criteria => ({
              type: "listItem",
              content: [{
                type: "paragraph",
                content: [{ type: "text", text: criteria }]
              }]
            }))
          },
          ...(story.technicalNotes ? [
            {
              type: "heading",
              attrs: { level: 3 },
              content: [{ type: "text", text: "Technical Notes" }]
            },
            {
              type: "paragraph",
              content: [{ type: "text", text: story.technicalNotes }]
            }
          ] : [])
        ]
      };

      const issueData = {
        fields: {
          project: { key: jiraProjectKey },
          parent: { key: parentKey },
          summary: story.title,
          description: description,
          issuetype: { name: "Subtask" },
          labels: story.labels || []
        }
      };

      const response = await fetch(`${jiraBaseUrl}/issue`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${auth}`,
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(issueData)
      });

      if (response.ok) {
        const data = await response.json();
        // Update the story with parent reference
        await storage.updateUserStory(storyId, { 
          parentJiraKey: parentKey,
          jiraKey: data.key 
        });
        res.json({ 
          storyKey: story.storyKey, 
          jiraKey: data.key, 
          parentKey,
          message: `Created subtask ${data.key} under ${parentKey}` 
        });
      } else {
        const errorData = await response.text();
        console.error(`JIRA API error:`, errorData);
        res.status(response.status).json({ error: `Failed to create subtask: ${response.status}` });
      }
    } catch (error) {
      console.error("Error creating JIRA subtask:", error);
      res.status(500).json({ error: "Failed to create JIRA subtask" });
    }
  });

  return httpServer;
}

// Helper function to extract plain text from Atlassian Document Format
function extractTextFromADF(adf: any): string {
  if (!adf) return "";
  if (typeof adf === "string") return adf;
  
  let text = "";
  
  function traverse(node: any) {
    if (node.text) {
      text += node.text + " ";
    }
    if (node.content && Array.isArray(node.content)) {
      node.content.forEach(traverse);
    }
  }
  
  traverse(adf);
  return text.trim();
}
