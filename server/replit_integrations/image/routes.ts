import type { Express, Request, Response } from "express";

/**
 * Image generation routes are disabled because PWC GenAI does not support image generation.
 * These routes return errors indicating the feature is unavailable.
 */

export function registerImageRoutes(app: Express): void {
  app.post("/api/generate-image", async (req: Request, res: Response) => {
    res.status(501).json({ 
      error: "Image generation is not supported. PWC GenAI only supports text generation. " +
             "Please use an external image generation service if needed." 
    });
  });
}

