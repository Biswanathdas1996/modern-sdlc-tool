"""Knowledge base service for document management and search."""
from typing import List, Dict, Any, Optional
from pymongo.database import Database
from core.database import get_db
from core.logging import log_info, log_error
from utils.text import chunk_text
import re


class KnowledgeBaseService:
    """Service for knowledge base operations."""
    
    CHUNKS_COLLECTION = "knowledge_chunks"
    DOCUMENTS_COLLECTION = "knowledge_documents"
    
    def __init__(self, db: Database):
        self.db = db
        
    def ingest_document(
        self, 
        document_id: str, 
        project_id: str, 
        filename: str, 
        content: str
    ) -> int:
        """Ingest a document into the knowledge base."""
        collection = self.db[self.CHUNKS_COLLECTION]
        
        # Delete existing chunks
        collection.delete_many({"documentId": document_id})
        
        # Create chunks
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
                log_error(f"Error processing chunk {i}", "kb", error)
        
        log_info(f"Ingested {inserted_count} chunks for {filename}", "kb")
        return inserted_count
    
    def search_knowledge_base(
        self, 
        project_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base."""
        collection = self.db[self.CHUNKS_COLLECTION]
        
        log_info(f"Searching KB: \"{query[:100]}...\"", "kb")
        
        total_chunks = collection.count_documents({})
        log_info(f"Total chunks in KB: {total_chunks}", "kb")
        
        # Extract keywords
        keywords = [w for w in query.lower().split() if len(w) > 2]
        log_info(f"Keywords: {', '.join(keywords[:10])}", "kb")
        
        if not keywords:
            log_info("No keywords, returning recent chunks", "kb")
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
            # Use regex patterns for search
            regex_patterns = [re.compile(kw, re.IGNORECASE) for kw in keywords]
            
            results = list(collection.find({
                "$or": [{"content": pattern} for pattern in regex_patterns]
            }).limit(limit * 2))
            
            log_info(f"Found {len(results)} matching chunks", "kb")
            
            # Score results
            scored_results = []
            for doc in results:
                content_lower = doc.get("content", "").lower()
                match_count = sum(1 for kw in keywords if kw in content_lower)
                scored_results.append({
                    "content": doc.get("content", ""),
                    "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                    "score": match_count / len(keywords) if keywords else 0
                })
            
            # Sort by score and limit
            final_results = sorted(
                scored_results, 
                key=lambda x: x["score"], 
                reverse=True
            )[:limit]
            
            filenames = [r["filename"] for r in final_results]
            log_info(f"Returning {len(final_results)} results from: {', '.join(filenames)}", "kb")
            return final_results
            
        except Exception as error:
            log_error("Text search error", "kb", error)
            return []
    
    def delete_document_chunks(self, document_id: str):
        """Delete all chunks for a document."""
        collection = self.db[self.CHUNKS_COLLECTION]
        result = collection.delete_many({"documentId": document_id})
        log_info(f"Deleted {result.deleted_count} chunks for document {document_id}", "kb")
    
    def get_knowledge_stats(self, project_id: str) -> Dict[str, int]:
        """Get knowledge base statistics."""
        collection = self.db[self.CHUNKS_COLLECTION]
        
        pipeline = [
            {"$group": {"_id": "$documentId", "chunks": {"$sum": 1}}},
            {
                "$group": {
                    "_id": None,
                    "documentCount": {"$sum": 1},
                    "chunkCount": {"$sum": "$chunks"}
                }
            }
        ]
        
        result = list(collection.aggregate(pipeline))
        
        if not result:
            return {"documentCount": 0, "chunkCount": 0}
        
        return {
            "documentCount": result[0].get("documentCount", 0),
            "chunkCount": result[0].get("chunkCount", 0)
        }


def get_kb_service() -> KnowledgeBaseService:
    """Dependency for getting KB service."""
    return KnowledgeBaseService(get_db())
