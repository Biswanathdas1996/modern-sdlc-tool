import type { Express, Request, Response } from "express";
import { chatStorage } from "./storage";

// PWC GenAI configuration
const GENAI_ENDPOINT = process.env.PWC_GENAI_ENDPOINT_URL!;
const API_KEY = process.env.PWC_GENAI_API_KEY!;
const BEARER_TOKEN = process.env.PWC_GENAI_BEARER_TOKEN!;

async function callPwcGenAI(prompt: string): Promise<string> {
  if (!API_KEY || !BEARER_TOKEN || !GENAI_ENDPOINT) {
    throw new Error("PWC GenAI credentials not configured");
  }

  const response = await fetch(GENAI_ENDPOINT, {
    method: "POST",
    headers: {
      accept: "application/json",
      "API-Key": API_KEY,
      Authorization: `Bearer ${BEARER_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "vertex_ai.gemini-2.0-flash",
      prompt,
      temperature: 0.7,
      top_p: 1,
      stream: false,
    }),
  });

  if (!response.ok) {
    throw new Error(`PWC GenAI API error: ${response.status}`);
  }

  const data = await response.json();
  return data.content || data.response || data.text || JSON.stringify(data);
}

export function registerChatRoutes(app: Express): void {
  // Get all conversations
  app.get("/api/conversations", async (req: Request, res: Response) => {
    try {
      const conversations = await chatStorage.getAllConversations();
      res.json(conversations);
    } catch (error) {
      console.error("Error fetching conversations:", error);
      res.status(500).json({ error: "Failed to fetch conversations" });
    }
  });

  // Get single conversation with messages
  app.get("/api/conversations/:id", async (req: Request, res: Response) => {
    try {
      const id = parseInt(req.params.id as string);
      const conversation = await chatStorage.getConversation(id);
      if (!conversation) {
        return res.status(404).json({ error: "Conversation not found" });
      }
      const messages = await chatStorage.getMessagesByConversation(id);
      res.json({ ...conversation, messages });
    } catch (error) {
      console.error("Error fetching conversation:", error);
      res.status(500).json({ error: "Failed to fetch conversation" });
    }
  });

  // Create new conversation
  app.post("/api/conversations", async (req: Request, res: Response) => {
    try {
      const { title } = req.body;
      const conversation = await chatStorage.createConversation(title || "New Chat");
      res.status(201).json(conversation);
    } catch (error) {
      console.error("Error creating conversation:", error);
      res.status(500).json({ error: "Failed to create conversation" });
    }
  });

  // Delete conversation
  app.delete("/api/conversations/:id", async (req: Request, res: Response) => {
    try {
      const id = parseInt(req.params.id as string);
      await chatStorage.deleteConversation(id);
      res.status(204).send();
    } catch (error) {
      console.error("Error deleting conversation:", error);
      res.status(500).json({ error: "Failed to delete conversation" });
    }
  });

  // Send message and get AI response (non-streaming with PWC GenAI)
  app.post("/api/conversations/:id/messages", async (req: Request, res: Response) => {
    try {
      const conversationId = parseInt(req.params.id as string);
      const { content } = req.body;

      // Save user message
      await chatStorage.createMessage(conversationId, "user", content);

      // Get conversation history for context
      const messages = await chatStorage.getMessagesByConversation(conversationId);
      const chatHistory = messages.map((m) => `${m.role}: ${m.content}`).join("\n");

      // Set up SSE for compatibility
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");

      // Build prompt with conversation history
      const prompt = `You are a helpful assistant. Here is the conversation history:\n\n${chatHistory}\n\nRespond to the latest user message.`;

      // Call PWC GenAI (non-streaming)
      const fullResponse = await callPwcGenAI(prompt);

      // Send full response as a single chunk
      res.write(`data: ${JSON.stringify({ content: fullResponse })}\n\n`);

      // Save assistant message
      await chatStorage.createMessage(conversationId, "assistant", fullResponse);

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } catch (error) {
      console.error("Error sending message:", error);
      // Check if headers already sent (SSE streaming started)
      if (res.headersSent) {
        res.write(`data: ${JSON.stringify({ error: "Failed to send message" })}\n\n`);
        res.end();
      } else {
        res.status(500).json({ error: "Failed to send message" });
      }
    }
  });
}

