import type { Express, Request, Response } from "express";
import { createServer, type Server } from "http";
import multer from "multer";
import { z } from "zod";
import { storage } from "./storage";
import { analyzeRepository, generateDocumentation, generateBRD, generateTestCases, generateTestData, generateUserStories, transcribeAudio } from "./ai";

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
      const project = await storage.getProject(req.params.id);
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
                await storage.createDocumentation(documentation);
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
      const brd = await storage.getCurrentBRD();
      if (!brd) {
        return res.status(400).json({ error: "No BRD found. Please generate a BRD first." });
      }

      const projects = await storage.getAllProjects();
      const documentation = projects.length > 0 ? await storage.getDocumentation(projects[0].id) : null;

      const userStories = await generateUserStories(brd, documentation || null);
      if (!userStories || userStories.length === 0) {
        return res.status(500).json({ error: "Failed to generate user stories - no stories returned" });
      }
      
      const savedStories = await storage.createUserStories(userStories);
      res.json(savedStories);
    } catch (error) {
      console.error("Error generating user stories:", error);
      res.status(500).json({ error: "Failed to generate user stories" });
    }
  });

  return httpServer;
}
