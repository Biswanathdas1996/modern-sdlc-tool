import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

client: Optional[MongoClient] = None
db: Optional[Database] = None

DB_NAME = "docugen_knowledge"
CHUNKS_COLLECTION = "knowledge_chunks"
DOCUMENTS_COLLECTION = "knowledge_documents"


def connect_mongodb() -> Database:
    global client, db
    
    if db is not None:
        return db

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise ValueError("MONGODB_URI environment variable is not set")

    try:
        client = MongoClient(uri)
        db = client[DB_NAME]
        print("Connected to MongoDB Atlas")
        ensure_vector_index()
        return db
    except Exception as error:
        print(f"Failed to connect to MongoDB: {error}")
        raise


def ensure_vector_index():
    global db
    if db is None:
        return

    collection = db[CHUNKS_COLLECTION]

    try:
        indexes = list(collection.list_indexes())
        has_vector_index = any(idx.get("name") == "vector_index" for idx in indexes)

        if not has_vector_index:
            print("Creating text index for search...")
            collection.create_index([("content", "text")], name="text_search_index")
            print("Text search index created")
    except Exception as error:
        print(f"Index might already exist or requires Atlas UI setup: {error}")


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        
        if end < len(text):
            last_period = text.rfind(".", start, end)
            last_newline = text.rfind("\n", start, end)
            break_point = max(last_period, last_newline)
            if break_point > start + chunk_size // 2:
                end = break_point + 1

        chunks.append(text[start:min(end, len(text))].strip())
        start = end - overlap
        
        if start >= len(text) - overlap:
            break

    return [chunk for chunk in chunks if len(chunk) > 50]


def ingest_document(document_id: str, project_id: str, filename: str, content: str) -> int:
    database = connect_mongodb()
    collection = database[CHUNKS_COLLECTION]

    collection.delete_many({"documentId": document_id})

    chunks = chunk_text(content)
    inserted_count = 0

    for i, chunk in enumerate(chunks):
        try:
            chunk_doc = {
                "documentId": document_id,
                "projectId": project_id,
                "content": chunk,
                "chunkIndex": i,
                "metadata": {
                    "filename": filename,
                    "section": f"Chunk {i + 1} of {len(chunks)}",
                },
                "contentLower": chunk.lower(),
            }

            collection.insert_one(chunk_doc)
            inserted_count += 1
        except Exception as error:
            print(f"Error processing chunk {i}: {error}")

    print(f"Ingested {inserted_count} chunks for document {filename}")
    return inserted_count


def search_knowledge_base(project_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    database = connect_mongodb()
    collection = database[CHUNKS_COLLECTION]

    print(f"[KB Search] Searching globally, query: \"{query[:100]}...\"")

    total_chunks = collection.count_documents({})
    print(f"[KB Search] Total chunks in knowledge base: {total_chunks}")

    keywords = [w for w in query.lower().split() if len(w) > 2]
    print(f"[KB Search] Keywords extracted: {', '.join(keywords[:10])}{'...' if len(keywords) > 10 else ''}")

    if not keywords:
        print("[KB Search] No keywords, returning recent chunks")
        results = list(collection.find({}).limit(limit))
        return [
            {
                "content": doc.get("content", ""),
                "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                "score": 0.5
            }
            for doc in results
        ]

    try:
        regex_patterns = [re.compile(kw, re.IGNORECASE) for kw in keywords]
        
        results = list(collection.find({
            "$or": [{"content": pattern} for pattern in regex_patterns]
        }).limit(limit * 2))

        print(f"[KB Search] Found {len(results)} matching chunks")

        scored_results = []
        for doc in results:
            content_lower = doc.get("content", "").lower()
            match_count = sum(1 for kw in keywords if kw in content_lower)
            scored_results.append({
                "content": doc.get("content", ""),
                "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                "score": match_count / len(keywords) if keywords else 0
            })

        final_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)[:limit]
        
        print(f"[KB Search] Returning {len(final_results)} results from files: {', '.join([r['filename'] for r in final_results])}")
        return final_results
    except Exception as error:
        print(f"[KB Search] Text search error: {error}")
        return []


def delete_document_chunks(document_id: str):
    database = connect_mongodb()
    collection = database[CHUNKS_COLLECTION]
    collection.delete_many({"documentId": document_id})


def delete_project_knowledge(project_id: str):
    database = connect_mongodb()
    collection = database[CHUNKS_COLLECTION]
    collection.delete_many({"projectId": project_id})


def get_knowledge_stats(project_id: str) -> Dict[str, int]:
    database = connect_mongodb()
    collection = database[CHUNKS_COLLECTION]

    pipeline = [
        {"$group": {"_id": "$documentId", "chunks": {"$sum": 1}}},
        {"$group": {"_id": None, "documentCount": {"$sum": 1}, "chunkCount": {"$sum": "$chunks"}}}
    ]

    result = list(collection.aggregate(pipeline))

    if not result:
        return {"documentCount": 0, "chunkCount": 0}

    return {
        "documentCount": result[0].get("documentCount", 0),
        "chunkCount": result[0].get("chunkCount", 0)
    }


def create_knowledge_document_in_mongo(doc: Dict[str, Any]) -> Dict[str, Any]:
    import random
    import string
    
    database = connect_mongodb()
    collection = database[DOCUMENTS_COLLECTION]

    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    new_doc = {
        **doc,
        "id": f"doc_{int(datetime.utcnow().timestamp() * 1000)}_{random_suffix}",
        "chunkCount": 0,
        "status": "processing",
        "errorMessage": None,
        "createdAt": datetime.utcnow().isoformat(),
    }

    collection.insert_one(new_doc)
    return new_doc


def get_knowledge_documents_from_mongo() -> List[Dict[str, Any]]:
    database = connect_mongodb()
    collection = database[DOCUMENTS_COLLECTION]

    docs = list(collection.find({}).sort("createdAt", -1))
    return [
        {
            "id": doc.get("id", ""),
            "projectId": doc.get("projectId", ""),
            "filename": doc.get("filename", ""),
            "originalName": doc.get("originalName", ""),
            "contentType": doc.get("contentType", ""),
            "size": doc.get("size", 0),
            "chunkCount": doc.get("chunkCount", 0),
            "status": doc.get("status", "ready"),
            "errorMessage": doc.get("errorMessage"),
            "createdAt": doc.get("createdAt", ""),
        }
        for doc in docs
    ]


def update_knowledge_document_in_mongo(id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    database = connect_mongodb()
    collection = database[DOCUMENTS_COLLECTION]

    result = collection.find_one_and_update(
        {"id": id},
        {"$set": updates},
        return_document=True
    )

    if not result:
        return None

    return {
        "id": result.get("id", ""),
        "projectId": result.get("projectId", ""),
        "filename": result.get("filename", ""),
        "originalName": result.get("originalName", ""),
        "contentType": result.get("contentType", ""),
        "size": result.get("size", 0),
        "chunkCount": result.get("chunkCount", 0),
        "status": result.get("status", "ready"),
        "errorMessage": result.get("errorMessage"),
        "createdAt": result.get("createdAt", ""),
    }


def delete_knowledge_document_from_mongo(id: str) -> bool:
    database = connect_mongodb()
    collection = database[DOCUMENTS_COLLECTION]

    result = collection.delete_one({"id": id})
    return result.deleted_count > 0
