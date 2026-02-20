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
                log_error(f"Error processing chunk {i}", "kb", error)
        
        log_info(f"Ingested {inserted_count} chunks for {filename} (project: {project_id})", "kb")
        return inserted_count
    
    def _project_filter(self, project_id: str) -> Dict[str, Any]:
        """Build a MongoDB filter for project scoping."""
        if project_id and project_id != "global":
            return {"projectId": project_id}
        return {}
    
    def search_knowledge_base(
        self, 
        project_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base with project-scoped relevance scoring."""
        collection = self.db[self.CHUNKS_COLLECTION]
        
        project_filter = self._project_filter(project_id)
        
        log_info(f"Searching KB (project: {project_id}): \"{query[:100]}...\"", "kb")
        
        total_chunks = collection.count_documents(project_filter)
        log_info(f"Total chunks in KB for project {project_id}: {total_chunks}", "kb")
        
        if total_chunks == 0:
            log_info(f"No chunks found for project {project_id}", "kb")
            return []
        
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'are', 'was', 'were', 'been', 'have', 'has'}
        keywords = [w for w in query.lower().split() if len(w) > 2 and w not in stop_words]
        log_info(f"Extracted keywords: {', '.join(keywords[:10])}", "kb")
        
        if not keywords:
            log_info("No keywords, returning recent project chunks", "kb")
            results = list(collection.find(project_filter).limit(limit))
            return [
                {
                    "content": doc.get("content", ""),
                    "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                    "score": 0.5
                }
                for doc in results
            ]
        
        try:
            escaped_keywords = [re.escape(kw) for kw in keywords]
            
            search_filter = {
                **project_filter,
                "$or": [{"content": {"$regex": kw, "$options": "i"}} for kw in escaped_keywords]
            }
            
            results = list(collection.find(search_filter).limit(limit * 3))
            
            log_info(f"Found {len(results)} matching chunks for project {project_id}", "kb")
            
            scored_results = []
            for doc in results:
                content = doc.get("content", "")
                content_lower = content.lower()
                
                match_count = sum(1 for kw in keywords if kw in content_lower)
                total_occurrences = sum(content_lower.count(kw) for kw in keywords)
                
                position_score = 0
                for kw in keywords:
                    idx = content_lower.find(kw)
                    if idx != -1:
                        position_score += (1 - (idx / max(len(content_lower), 1)))
                
                phrase_score = 0
                query_lower = query.lower()
                words = query_lower.split()
                for i in range(len(words) - 1):
                    two_word_phrase = f"{words[i]} {words[i+1]}"
                    if two_word_phrase in content_lower:
                        phrase_score += 2
                for i in range(len(words) - 2):
                    three_word_phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
                    if three_word_phrase in content_lower:
                        phrase_score += 3
                
                base_score = match_count / len(keywords) if keywords else 0
                frequency_bonus = min(total_occurrences * 0.1, 0.5)
                position_bonus = (position_score / len(keywords)) * 0.3 if keywords else 0
                phrase_bonus = min(phrase_score * 0.1, 0.4)
                
                final_score = base_score + frequency_bonus + position_bonus + phrase_bonus
                
                scored_results.append({
                    "content": content,
                    "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                    "score": final_score,
                    "matches": match_count,
                    "occurrences": total_occurrences
                })
            
            final_results = sorted(
                scored_results, 
                key=lambda x: x["score"], 
                reverse=True
            )[:limit]
            
            for i, r in enumerate(final_results[:3]):
                log_info(f"Top result {i+1}: {r['filename']} (score: {r['score']:.3f}, matches: {r['matches']}, occurrences: {r['occurrences']})", "kb")
            
            return final_results
            
        except Exception as error:
            log_error("Text search error", "kb", error)
            return []
    
    def delete_document_chunks(self, document_id: str) -> int:
        """Delete all chunks for a document from the MongoDB cluster."""
        collection = self.db[self.CHUNKS_COLLECTION]
        
        chunk_count = collection.count_documents({"documentId": document_id})
        log_info(f"Found {chunk_count} chunks to delete for document {document_id}", "kb")
        
        result = collection.delete_many({"documentId": document_id})
        deleted_count = result.deleted_count
        
        remaining = collection.count_documents({"documentId": document_id})
        if remaining > 0:
            log_error(f"Failed to delete all chunks. {remaining} chunks still remain for document {document_id}", "kb", None)
        else:
            log_info(f"Successfully deleted {deleted_count} chunks from MongoDB cluster for document {document_id}", "kb")
        
        return deleted_count
    
    def get_knowledge_stats(self, project_id: str) -> Dict[str, int]:
        """Get knowledge base statistics scoped to a project."""
        collection = self.db[self.CHUNKS_COLLECTION]
        
        project_filter = self._project_filter(project_id)
        
        pipeline = [
            {"$match": project_filter} if project_filter else {"$match": {}},
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
    
    def get_knowledge_documents(self, project_id: str) -> List[Dict[str, Any]]:
        """Get knowledge documents scoped to a project."""
        collection = self.db[self.DOCUMENTS_COLLECTION]
        
        project_filter = self._project_filter(project_id)
        documents = list(collection.find(project_filter).sort("uploadedAt", -1))
        
        for doc in documents:
            if "id" not in doc and "_id" in doc:
                doc["id"] = str(doc["_id"])
            if "_id" in doc:
                del doc["_id"]
        
        return documents
    
    def create_knowledge_document(self, doc_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a knowledge document record."""
        import uuid
        from datetime import datetime
        
        collection = self.db[self.DOCUMENTS_COLLECTION]
        doc = {
            "id": str(uuid.uuid4()),
            "uploadedAt": datetime.utcnow().isoformat(),
            **doc_data
        }
        collection.insert_one(doc)
        if "_id" in doc:
            del doc["_id"]
        return doc
    
    def update_knowledge_document(self, document_id: str, updates: Dict[str, Any]) -> bool:
        """Update a knowledge document record."""
        collection = self.db[self.DOCUMENTS_COLLECTION]
        result = collection.update_one(
            {"id": document_id},
            {"$set": updates}
        )
        return result.modified_count > 0

    def delete_knowledge_document(self, document_id: str) -> bool:
        """Delete a knowledge document from the MongoDB cluster."""
        collection = self.db[self.DOCUMENTS_COLLECTION]
        
        doc = collection.find_one({"id": document_id})
        if not doc:
            log_info(f"Document {document_id} not found in collection", "kb")
            return False
        
        result = collection.delete_one({"id": document_id})
        deleted = result.deleted_count > 0
        
        if deleted:
            log_info(f"Successfully deleted document record {document_id} from MongoDB cluster", "kb")
        else:
            log_error(f"Failed to delete document record {document_id}", "kb", None)
        
        return deleted
    
    def delete_knowledge_document_complete(self, document_id: str) -> Dict[str, Any]:
        """Complete deletion of a knowledge document including all chunks and indexes."""
        log_info(f"Starting complete deletion for document {document_id}", "kb")
        
        chunks_deleted = self.delete_document_chunks(document_id)
        doc_deleted = self.delete_knowledge_document(document_id)
        
        result = {
            "documentId": document_id,
            "chunksDeleted": chunks_deleted,
            "documentDeleted": doc_deleted,
            "success": doc_deleted
        }
        
        if doc_deleted:
            log_info(f"Complete deletion successful for {document_id}: {chunks_deleted} chunks + 1 document removed from MongoDB", "kb")
        else:
            log_info(f"Document {document_id} not found, but cleaned up {chunks_deleted} orphaned chunks", "kb")
        
        return result
    
    def cleanup_orphaned_chunks(self) -> int:
        """Clean up chunks that have no corresponding document record."""
        chunks_collection = self.db[self.CHUNKS_COLLECTION]
        docs_collection = self.db[self.DOCUMENTS_COLLECTION]
        
        chunk_doc_ids = chunks_collection.distinct("documentId")
        log_info(f"Found {len(chunk_doc_ids)} unique document IDs in chunks", "kb")
        
        valid_doc_ids = set(doc["id"] for doc in docs_collection.find({}, {"id": 1}))
        log_info(f"Found {len(valid_doc_ids)} valid documents", "kb")
        
        orphaned_ids = [doc_id for doc_id in chunk_doc_ids if doc_id not in valid_doc_ids]
        
        if not orphaned_ids:
            log_info("No orphaned chunks found", "kb")
            return 0
        
        log_info(f"Found {len(orphaned_ids)} orphaned document IDs with chunks", "kb")
        
        total_deleted = 0
        for doc_id in orphaned_ids:
            result = chunks_collection.delete_many({"documentId": doc_id})
            total_deleted += result.deleted_count
            log_info(f"Deleted {result.deleted_count} orphaned chunks for document {doc_id}", "kb")
        
        log_info(f"Cleanup complete: Removed {total_deleted} total orphaned chunks from MongoDB", "kb")
        return total_deleted
    
    def verify_document_deletion(self, document_id: str) -> Dict[str, Any]:
        """Verify that a document and all its chunks are completely deleted."""
        chunks_collection = self.db[self.CHUNKS_COLLECTION]
        docs_collection = self.db[self.DOCUMENTS_COLLECTION]
        
        doc_exists = docs_collection.count_documents({"id": document_id}) > 0
        chunk_count = chunks_collection.count_documents({"documentId": document_id})
        
        is_clean = not doc_exists and chunk_count == 0
        
        result = {
            "documentId": document_id,
            "documentExists": doc_exists,
            "remainingChunks": chunk_count,
            "isCompletelyDeleted": is_clean
        }
        
        if is_clean:
            log_info(f"Verification passed: Document {document_id} is completely deleted from MongoDB", "kb")
        else:
            log_error(f"Verification failed: Document {document_id} still has data in MongoDB (doc: {doc_exists}, chunks: {chunk_count})", "kb", None)
        
        return result


def get_kb_service() -> KnowledgeBaseService:
    """Dependency for getting KB service."""
    return KnowledgeBaseService(get_db())
