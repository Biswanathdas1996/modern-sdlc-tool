import { MongoClient, Db, Collection } from "mongodb";
import OpenAI from "openai";
import type { KnowledgeChunk, KnowledgeDocument } from "@shared/schema";

const openai = new OpenAI({
  apiKey: process.env.AI_INTEGRATIONS_OPENAI_API_KEY,
  baseURL: process.env.AI_INTEGRATIONS_OPENAI_BASE_URL,
});

let client: MongoClient | null = null;
let db: Db | null = null;

const DB_NAME = "docugen_knowledge";
const CHUNKS_COLLECTION = "knowledge_chunks";
const DOCUMENTS_COLLECTION = "knowledge_documents";

export async function connectMongoDB(): Promise<Db> {
  if (db) return db;

  const uri = process.env.MONGODB_URI;
  if (!uri) {
    throw new Error("MONGODB_URI environment variable is not set");
  }

  try {
    client = new MongoClient(uri);
    await client.connect();
    db = client.db(DB_NAME);
    console.log("Connected to MongoDB Atlas");

    await ensureVectorIndex();
    return db;
  } catch (error) {
    console.error("Failed to connect to MongoDB:", error);
    throw error;
  }
}

async function ensureVectorIndex(): Promise<void> {
  if (!db) return;

  const collection = db.collection(CHUNKS_COLLECTION);

  try {
    const indexes = await collection.listIndexes().toArray();
    const hasVectorIndex = indexes.some(idx => idx.name === "vector_index");

    if (!hasVectorIndex) {
      console.log("Creating vector search index...");
      await db.command({
        createSearchIndexes: CHUNKS_COLLECTION,
        indexes: [
          {
            name: "vector_index",
            type: "vectorSearch",
            definition: {
              fields: [
                {
                  type: "vector",
                  path: "embedding",
                  numDimensions: 1536,
                  similarity: "cosine"
                }
              ]
            }
          }
        ]
      });
      console.log("Vector search index created");
    }
  } catch (error: any) {
    if (error.codeName !== "IndexAlreadyExists") {
      console.log("Vector index might already exist or requires Atlas UI setup:", error.message);
    }
  }
}

export async function generateEmbedding(text: string): Promise<number[]> {
  const response = await openai.embeddings.create({
    model: "text-embedding-3-small",
    input: text,
  });
  return response.data[0].embedding;
}

function chunkText(text: string, chunkSize: number = 1000, overlap: number = 200): string[] {
  const chunks: string[] = [];
  let start = 0;

  while (start < text.length) {
    let end = start + chunkSize;
    
    if (end < text.length) {
      const lastPeriod = text.lastIndexOf(".", end);
      const lastNewline = text.lastIndexOf("\n", end);
      const breakPoint = Math.max(lastPeriod, lastNewline);
      if (breakPoint > start + chunkSize / 2) {
        end = breakPoint + 1;
      }
    }

    chunks.push(text.substring(start, Math.min(end, text.length)).trim());
    start = end - overlap;
    
    if (start >= text.length - overlap) break;
  }

  return chunks.filter(chunk => chunk.length > 50);
}

export async function ingestDocument(
  documentId: string,
  projectId: string,
  filename: string,
  content: string
): Promise<number> {
  const database = await connectMongoDB();
  const collection = database.collection(CHUNKS_COLLECTION);

  await collection.deleteMany({ documentId });

  const chunks = chunkText(content);
  let insertedCount = 0;

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    
    try {
      const embedding = await generateEmbedding(chunk);
      
      const chunkDoc: KnowledgeChunk & { embedding: number[] } = {
        documentId,
        projectId,
        content: chunk,
        chunkIndex: i,
        embedding,
        metadata: {
          filename,
          section: `Chunk ${i + 1} of ${chunks.length}`,
        },
      };

      await collection.insertOne(chunkDoc);
      insertedCount++;
    } catch (error) {
      console.error(`Error processing chunk ${i}:`, error);
    }
  }

  console.log(`Ingested ${insertedCount} chunks for document ${filename}`);
  return insertedCount;
}

export async function searchKnowledgeBase(
  projectId: string,
  query: string,
  limit: number = 5
): Promise<{ content: string; filename: string; score: number }[]> {
  const database = await connectMongoDB();
  const collection = database.collection(CHUNKS_COLLECTION);

  try {
    const queryEmbedding = await generateEmbedding(query);

    const pipeline = [
      {
        $vectorSearch: {
          index: "vector_index",
          path: "embedding",
          queryVector: queryEmbedding,
          numCandidates: limit * 10,
          limit: limit,
          filter: { projectId: projectId }
        }
      },
      {
        $project: {
          content: 1,
          "metadata.filename": 1,
          score: { $meta: "vectorSearchScore" }
        }
      }
    ];

    const results = await collection.aggregate(pipeline).toArray();
    
    return results.map(doc => ({
      content: doc.content,
      filename: doc.metadata?.filename || "Unknown",
      score: doc.score || 0
    }));
  } catch (error: any) {
    console.error("Vector search error:", error.message);
    
    console.log("Falling back to text-based search...");
    const keywords = query.toLowerCase().split(/\s+/).filter(w => w.length > 3);
    
    if (keywords.length === 0) {
      return [];
    }

    const regexPattern = keywords.map(k => `(?=.*${k})`).join("");
    
    const results = await collection
      .find({
        projectId,
        content: { $regex: regexPattern, $options: "i" }
      })
      .limit(limit)
      .toArray();

    return results.map(doc => ({
      content: doc.content,
      filename: doc.metadata?.filename || "Unknown",
      score: 0.5
    }));
  }
}

export async function deleteDocumentChunks(documentId: string): Promise<void> {
  const database = await connectMongoDB();
  const collection = database.collection(CHUNKS_COLLECTION);
  await collection.deleteMany({ documentId });
}

export async function deleteProjectKnowledge(projectId: string): Promise<void> {
  const database = await connectMongoDB();
  const collection = database.collection(CHUNKS_COLLECTION);
  await collection.deleteMany({ projectId });
}

export async function getKnowledgeStats(projectId: string): Promise<{ documentCount: number; chunkCount: number }> {
  const database = await connectMongoDB();
  const collection = database.collection(CHUNKS_COLLECTION);
  
  const pipeline = [
    { $match: { projectId } },
    {
      $group: {
        _id: "$documentId",
        chunks: { $sum: 1 }
      }
    },
    {
      $group: {
        _id: null,
        documentCount: { $sum: 1 },
        chunkCount: { $sum: "$chunks" }
      }
    }
  ];

  const result = await collection.aggregate(pipeline).toArray();
  
  if (result.length === 0) {
    return { documentCount: 0, chunkCount: 0 };
  }

  return {
    documentCount: result[0].documentCount,
    chunkCount: result[0].chunkCount
  };
}
