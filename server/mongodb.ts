import { MongoClient, Db, Collection } from "mongodb";
import type { KnowledgeChunk, KnowledgeDocument } from "@shared/schema";

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

export async function generateEmbedding(text: string): Promise<number[] | null> {
  // Replit AI Integrations doesn't support embeddings endpoint
  // Return null to use text-based search fallback
  return null;
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
      // Store chunk without embedding - using text-based search
      const chunkDoc = {
        documentId,
        projectId,
        content: chunk,
        chunkIndex: i,
        metadata: {
          filename,
          section: `Chunk ${i + 1} of ${chunks.length}`,
        },
        // Store lowercase content for text search
        contentLower: chunk.toLowerCase(),
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

  console.log(`[KB Search] Searching globally, query: "${query.substring(0, 100)}..."`);

  // Count total chunks in the knowledge base (all projectIds)
  const totalChunks = await collection.countDocuments({});
  console.log(`[KB Search] Total chunks in knowledge base: ${totalChunks}`);

  // Use text-based search (embeddings not available via Replit AI Integrations)
  const keywords = query.toLowerCase().split(/\s+/).filter(w => w.length > 2);
  console.log(`[KB Search] Keywords extracted: ${keywords.slice(0, 10).join(", ")}${keywords.length > 10 ? "..." : ""}`);
  
  if (keywords.length === 0) {
    // Return recent chunks if no keywords
    console.log(`[KB Search] No keywords, returning recent chunks`);
    const results = await collection
      .find({})
      .limit(limit)
      .toArray();
    
    return results.map(doc => ({
      content: doc.content,
      filename: doc.metadata?.filename || "Unknown",
      score: 0.5
    }));
  }

  try {
    // Build regex pattern for keyword matching - search ALL chunks globally
    const regexPatterns = keywords.map(kw => new RegExp(kw, "i"));
    
    const results = await collection
      .find({
        $or: regexPatterns.map(pattern => ({ content: pattern }))
      })
      .limit(limit * 2)
      .toArray();

    console.log(`[KB Search] Found ${results.length} matching chunks`);

    // Score results by keyword match count
    const scoredResults = results.map(doc => {
      const contentLower = doc.content.toLowerCase();
      let matchCount = 0;
      for (const kw of keywords) {
        if (contentLower.includes(kw)) matchCount++;
      }
      return {
        content: doc.content,
        filename: doc.metadata?.filename || "Unknown",
        score: matchCount / keywords.length
      };
    });

    // Sort by score and limit
    const finalResults = scoredResults
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
    
    console.log(`[KB Search] Returning ${finalResults.length} results from files: ${finalResults.map(r => r.filename).join(", ")}`);
    return finalResults;
  } catch (error: any) {
    console.error("[KB Search] Text search error:", error.message);
    return [];
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
  
  // Count all chunks globally (knowledge base is project-agnostic)
  const pipeline = [
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

// Knowledge Document CRUD operations (persisted in MongoDB)
export async function createKnowledgeDocumentInMongo(
  doc: Omit<KnowledgeDocument, "id" | "createdAt" | "chunkCount" | "status" | "errorMessage">
): Promise<KnowledgeDocument> {
  const database = await connectMongoDB();
  const collection = database.collection(DOCUMENTS_COLLECTION);
  
  const newDoc: KnowledgeDocument = {
    ...doc,
    id: `doc_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
    chunkCount: 0,
    status: "processing",
    errorMessage: null,
    createdAt: new Date().toISOString(),
  };
  
  await collection.insertOne(newDoc);
  return newDoc;
}

export async function getKnowledgeDocumentsFromMongo(): Promise<KnowledgeDocument[]> {
  const database = await connectMongoDB();
  const collection = database.collection(DOCUMENTS_COLLECTION);
  
  const docs = await collection.find({}).sort({ createdAt: -1 }).toArray();
  return docs.map(doc => ({
    id: doc.id,
    projectId: doc.projectId,
    filename: doc.filename,
    originalName: doc.originalName,
    contentType: doc.contentType,
    size: doc.size,
    chunkCount: doc.chunkCount || 0,
    status: doc.status || "ready",
    errorMessage: doc.errorMessage || null,
    createdAt: doc.createdAt,
  }));
}

export async function updateKnowledgeDocumentInMongo(
  id: string,
  updates: Partial<KnowledgeDocument>
): Promise<KnowledgeDocument | undefined> {
  const database = await connectMongoDB();
  const collection = database.collection(DOCUMENTS_COLLECTION);
  
  const result = await collection.findOneAndUpdate(
    { id },
    { $set: updates },
    { returnDocument: "after" }
  );
  
  if (!result) return undefined;
  
  return {
    id: result.id,
    projectId: result.projectId,
    filename: result.filename,
    originalName: result.originalName,
    contentType: result.contentType,
    size: result.size,
    chunkCount: result.chunkCount || 0,
    status: result.status || "ready",
    errorMessage: result.errorMessage || null,
    createdAt: result.createdAt,
  };
}

export async function deleteKnowledgeDocumentFromMongo(id: string): Promise<boolean> {
  const database = await connectMongoDB();
  const collection = database.collection(DOCUMENTS_COLLECTION);
  
  const result = await collection.deleteOne({ id });
  return result.deletedCount > 0;
}
