"""Knowledge base service for document management and search."""
from typing import List, Dict, Any, Optional
from pymongo.database import Database
from core.database import get_db
from core.logging import log_info, log_error
from utils.text import chunk_text
from utils.embeddings import generate_embeddings_batch, generate_embedding, cosine_similarity
import re


_initialized_collections = set()


def _sanitize_project_id(project_id: str) -> str:
    """Sanitize project_id for use in MongoDB collection names."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)


class KnowledgeBaseService:
    """Service for knowledge base operations with per-project collections."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def _chunks_collection_name(self, project_id: str) -> str:
        safe_id = _sanitize_project_id(project_id)
        return f"knowledge_chunks_{safe_id}"
    
    def _docs_collection_name(self, project_id: str) -> str:
        safe_id = _sanitize_project_id(project_id)
        return f"knowledge_documents_{safe_id}"
    
    def _ensure_project_indexes(self, project_id: str):
        global _initialized_collections
        
        safe_id = _sanitize_project_id(project_id)
        if safe_id in _initialized_collections:
            return
        
        chunks_name = self._chunks_collection_name(project_id)
        docs_name = self._docs_collection_name(project_id)
        
        chunks_col = self.db[chunks_name]
        docs_col = self.db[docs_name]
        
        try:
            existing = [idx.get("name") for idx in chunks_col.list_indexes()]
            
            if "text_search_index" not in existing:
                chunks_col.create_index(
                    [("content", "text")],
                    name="text_search_index"
                )
                log_info(f"Created text_search_index on {chunks_name}", "kb")
            
            if "documentId_1" not in existing:
                chunks_col.create_index(
                    [("documentId", 1)],
                    name="documentId_1"
                )
                log_info(f"Created documentId_1 index on {chunks_name}", "kb")
            
            doc_existing = [idx.get("name") for idx in docs_col.list_indexes()]
            
            if "id_1" not in doc_existing:
                docs_col.create_index(
                    [("id", 1)],
                    name="id_1"
                )
                log_info(f"Created id_1 index on {docs_name}", "kb")
            
            self._ensure_vector_index(chunks_col, chunks_name)
            
            _initialized_collections.add(safe_id)
            log_info(f"Indexes verified for project {project_id} (chunks: {chunks_name}, docs: {docs_name})", "kb")
            
        except Exception as error:
            log_error(f"Index setup error for project {project_id}", "kb", error)
    
    def _ensure_vector_index(self, collection, collection_name: str) -> str:
        """Create Atlas Vector Search index on the embedding field if not exists.
        Returns: 'created', 'exists', or 'error'
        """
        try:
            from pymongo.operations import SearchIndexModel
            
            existing_search = [idx.get("name") for idx in collection.list_search_indexes()]
            
            if "vector_index" not in existing_search:
                vector_index = SearchIndexModel(
                    definition={
                        "fields": [
                            {
                                "type": "vector",
                                "path": "embedding",
                                "numDimensions": 384,
                                "similarity": "cosine"
                            },
                            {
                                "type": "filter",
                                "path": "documentId"
                            },
                            {
                                "type": "filter",
                                "path": "projectId"
                            }
                        ]
                    },
                    name="vector_index",
                    type="vectorSearch"
                )
                collection.create_search_index(model=vector_index)
                log_info(f"Created vector_index on {collection_name}", "kb")
                return "created"
            
            log_info(f"vector_index already exists on {collection_name}", "kb")
            return "exists"
            
        except Exception as error:
            log_error(f"Vector index setup on {collection_name}", "kb", error)
            return "error"
    
    def _get_chunks_collection(self, project_id: str):
        self._ensure_project_indexes(project_id)
        return self.db[self._chunks_collection_name(project_id)]
    
    def _get_docs_collection(self, project_id: str):
        self._ensure_project_indexes(project_id)
        return self.db[self._docs_collection_name(project_id)]
        
    def ingest_document(
        self, 
        document_id: str, 
        project_id: str, 
        filename: str, 
        content: str,
        on_progress: Optional[callable] = None,
        image_count: int = 0,
        captioned_image_count: int = 0,
    ) -> int:
        """Ingest a document with paragraph-based chunking, embedding generation,
        and vector index creation/verification.
        
        The `content` parameter should already include image captions merged into
        the text stream (via ParsedContent.combined_text_with_captions) when
        multimodal parsing is used.
        
        Calls on_progress(step, detail) if provided."""
        def report(step: str, detail: str = ""):
            if on_progress:
                on_progress(step, detail)
        
        report("preparing", f"Setting up project collection for '{filename}'...")
        collection = self._get_chunks_collection(project_id)
        docs_col = self._get_docs_collection(project_id)
        
        docs_col.update_one(
            {"id": document_id},
            {"$set": {"rawContent": content}},
            upsert=False
        )
        
        collection.delete_many({"documentId": document_id})
        
        report("chunking", f"Splitting '{filename}' into semantic chunks...")
        chunks = chunk_text(content)
        total_chunks = len(chunks)
        avg_chars = sum(len(c) for c in chunks) // max(total_chunks, 1)
        log_info(f"Document '{filename}' split into {total_chunks} chunks (avg {avg_chars} chars)", "kb")
        multimodal_note = f" (includes {captioned_image_count} image captions)" if captioned_image_count > 0 else ""
        report("chunking_done", f"Created {total_chunks} chunks (avg {avg_chars} chars each){multimodal_note}")
        
        report("embedding", f"Generating vector embeddings for {total_chunks} chunks...")
        log_info(f"Generating embeddings for {total_chunks} chunks...", "kb")
        embeddings = generate_embeddings_batch(chunks)
        embedded_count = sum(1 for e in embeddings if e is not None)
        log_info(f"Generated {embedded_count}/{total_chunks} embeddings successfully", "kb")
        report("embedding_done", f"Generated {embedded_count}/{total_chunks} embeddings (BAAI/bge-small-en-v1.5, 384-dim)")
        
        report("storing", f"Storing {total_chunks} chunks in MongoDB collection...")
        inserted_count = 0
        
        for i, chunk in enumerate(chunks):
            try:
                has_image_caption = "[Image on " in chunk
                chunk_doc = {
                    "documentId": document_id,
                    "projectId": project_id,
                    "content": chunk,
                    "chunkIndex": i,
                    "totalChunks": total_chunks,
                    "metadata": {
                        "filename": filename,
                        "section": f"Chunk {i + 1} of {total_chunks}",
                        "charCount": len(chunk),
                        "hasImageCaption": has_image_caption,
                    },
                    "contentLower": chunk.lower(),
                }
                
                if embeddings[i] is not None:
                    chunk_doc["embedding"] = embeddings[i]
                    chunk_doc["embeddingModel"] = "BAAI/bge-small-en-v1.5"
                    chunk_doc["embeddingDimension"] = len(embeddings[i])
                
                collection.insert_one(chunk_doc)
                inserted_count += 1
            except Exception as error:
                log_error(f"Error processing chunk {i}", "kb", error)
        
        report("storing_done", f"Stored {inserted_count} chunks in {self._chunks_collection_name(project_id)}")
        
        report("indexing", "Creating/verifying Atlas Vector Search index for semantic search...")
        chunks_name = self._chunks_collection_name(project_id)
        index_status = self._ensure_vector_index(collection, chunks_name)
        if index_status == "created":
            report("indexing_done", f"Created new vector_index on {chunks_name} (building in background)")
        elif index_status == "exists":
            report("indexing_done", f"Vector search index verified on {chunks_name}")
        else:
            report("indexing_done", "Vector index setup encountered an issue; in-memory search will be used as fallback")
        
        img_summary = f", {captioned_image_count} image captions" if captioned_image_count > 0 else ""
        log_info(f"Ingested {inserted_count} chunks ({embedded_count} with embeddings{img_summary}) for '{filename}' into {chunks_name}", "kb")
        report("complete", f"Successfully ingested '{filename}': {inserted_count} chunks with {embedded_count} embeddings{img_summary}, vector index {index_status}")
        return inserted_count
    
    def search_knowledge_base(
        self, 
        project_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search using vector similarity only. Returns only chunks above the similarity threshold.
        No keyword fallback - if chunks don't meet the threshold, they are excluded entirely."""
        collection = self._get_chunks_collection(project_id)
        
        log_info(f"Searching KB collection {self._chunks_collection_name(project_id)}: \"{query[:100]}\"", "kb")
        
        total_chunks = collection.count_documents({})
        if total_chunks == 0:
            log_info(f"No chunks found in project {project_id} collection", "kb")
            return []
        
        has_embeddings = collection.count_documents({"embedding": {"$exists": True}}) > 0
        
        if has_embeddings:
            results = self._vector_search(collection, query, limit)
            if results:
                log_info(f"Vector search returned {len(results)} results (all above threshold)", "kb")
                return results
            log_info("No chunks met the similarity threshold — excluding all from context", "kb")
            return []
        
        log_info("No embeddings found in chunks, cannot perform semantic search — no results returned", "kb")
        return []
    
    MIN_SIMILARITY_SCORE = 0.55
    ATLAS_MIN_SCORE = 0.78
    VECTOR_INDEX_NAME = "vector_index"

    def _vector_search(self, collection, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search using Atlas $vectorSearch aggregation with the vector_index.
        Falls back to in-memory cosine similarity if Atlas index is unavailable.
        Only returns chunks with similarity >= MIN_SIMILARITY_SCORE."""
        query_embedding = generate_embedding(query)
        if query_embedding is None:
            log_error("Failed to generate query embedding", "kb")
            return []
        
        results = self._atlas_vector_search(collection, query_embedding, limit)
        if results is not None:
            return results
        
        log_info("Atlas vector search unavailable, using in-memory cosine similarity", "kb")
        return self._inmemory_vector_search(collection, query_embedding, limit)
    
    def _atlas_vector_search(self, collection, query_embedding: List[float], limit: int):
        """Use Atlas $vectorSearch aggregation pipeline with the project's vector_index."""
        try:
            has_index = any(
                idx.get("name") == self.VECTOR_INDEX_NAME and idx.get("queryable")
                for idx in collection.list_search_indexes()
            )
            if not has_index:
                return None
            
            num_candidates = max(limit * 10, 50)
            
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": self.VECTOR_INDEX_NAME,
                        "path": "embedding",
                        "queryVector": query_embedding,
                        "numCandidates": num_candidates,
                        "limit": limit * 3
                    }
                },
                {
                    "$project": {
                        "content": 1,
                        "metadata": 1,
                        "chunkIndex": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]
            
            raw_results = list(collection.aggregate(pipeline))
            
            results = []
            for doc in raw_results:
                score = doc.get("score", 0)
                if score < self.ATLAS_MIN_SCORE:
                    continue
                results.append({
                    "content": doc.get("content", ""),
                    "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                    "score": round(score, 4),
                    "chunkIndex": doc.get("chunkIndex", 0),
                    "searchMethod": "atlas_vector"
                })
            
            results = results[:limit]
            
            if results:
                log_info(f"Atlas vector search: returning {len(results)} results (index: {self.VECTOR_INDEX_NAME})", "kb")
            else:
                log_info(f"Atlas vector search: no chunks met minimum threshold ({self.ATLAS_MIN_SCORE})", "kb")
            
            for i, r in enumerate(results[:3]):
                log_info(f"Vector result {i+1}: {r['filename']} chunk#{r['chunkIndex']} (score: {r['score']:.4f})", "kb")
            
            return results
            
        except Exception as e:
            log_error(f"Atlas $vectorSearch failed: {e}", "kb")
            return None
    
    def _inmemory_vector_search(self, collection, query_embedding: List[float], limit: int) -> List[Dict[str, Any]]:
        """Fallback: fetch all chunks and compute cosine similarity in memory."""
        all_chunks = list(collection.find(
            {"embedding": {"$exists": True}},
            {"content": 1, "metadata": 1, "embedding": 1, "chunkIndex": 1}
        ))
        
        if not all_chunks:
            return []
        
        scored = []
        for doc in all_chunks:
            doc_embedding = doc.get("embedding")
            if not doc_embedding:
                continue
            
            similarity = cosine_similarity(query_embedding, doc_embedding)
            
            if similarity < self.MIN_SIMILARITY_SCORE:
                continue
            
            scored.append({
                "content": doc.get("content", ""),
                "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                "score": round(similarity, 4),
                "chunkIndex": doc.get("chunkIndex", 0),
                "searchMethod": "vector"
            })
        
        scored.sort(key=lambda x: x["score"], reverse=True)
        results = scored[:limit]
        
        if results:
            log_info(f"In-memory vector search: returning {len(results)} results", "kb")
        else:
            log_info(f"In-memory vector search: no chunks met minimum threshold ({self.MIN_SIMILARITY_SCORE})", "kb")
        
        for i, r in enumerate(results[:3]):
            log_info(f"Vector result {i+1}: {r['filename']} chunk#{r['chunkIndex']} (similarity: {r['score']:.4f})", "kb")
        
        return results
    
    def _keyword_search(self, collection, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback keyword-based search."""
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'are', 'was', 'were', 'been', 'have', 'has', 'not', 'but', 'its', 'can', 'will'}
        keywords = [w for w in query.lower().split() if len(w) > 2 and w not in stop_words]
        
        if not keywords:
            results = list(collection.find({}).limit(limit))
            return [
                {
                    "content": doc.get("content", ""),
                    "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                    "score": 0.5,
                    "searchMethod": "fallback"
                }
                for doc in results
            ]
        
        escaped_keywords = [re.escape(kw) for kw in keywords]
        search_filter = {
            "$or": [{"content": {"$regex": kw, "$options": "i"}} for kw in escaped_keywords]
        }
        
        results = list(collection.find(search_filter).limit(limit * 3))
        log_info(f"Keyword search found {len(results)} matching chunks", "kb")
        
        scored_results = []
        for doc in results:
            content = doc.get("content", "")
            content_lower = content.lower()
            
            match_count = sum(1 for kw in keywords if kw in content_lower)
            total_occurrences = sum(content_lower.count(kw) for kw in keywords)
            
            phrase_score = 0
            words = query.lower().split()
            for i in range(len(words) - 1):
                if f"{words[i]} {words[i+1]}" in content_lower:
                    phrase_score += 2
            for i in range(len(words) - 2):
                if f"{words[i]} {words[i+1]} {words[i+2]}" in content_lower:
                    phrase_score += 3
            
            base_score = match_count / len(keywords) if keywords else 0
            frequency_bonus = min(total_occurrences * 0.1, 0.5)
            phrase_bonus = min(phrase_score * 0.1, 0.4)
            
            scored_results.append({
                "content": content,
                "filename": doc.get("metadata", {}).get("filename", "Unknown"),
                "score": round(base_score + frequency_bonus + phrase_bonus, 4),
                "searchMethod": "keyword"
            })
        
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:limit]
    
    def delete_document_chunks(self, document_id: str, project_id: str) -> int:
        collection = self._get_chunks_collection(project_id)
        
        chunk_count = collection.count_documents({"documentId": document_id})
        log_info(f"Found {chunk_count} chunks to delete for document {document_id} in project {project_id}", "kb")
        
        result = collection.delete_many({"documentId": document_id})
        deleted_count = result.deleted_count
        
        remaining = collection.count_documents({"documentId": document_id})
        if remaining > 0:
            log_error(f"Failed to delete all chunks. {remaining} chunks still remain for document {document_id}", "kb", None)
        else:
            log_info(f"Successfully deleted {deleted_count} chunks for document {document_id} from {self._chunks_collection_name(project_id)}", "kb")
        
        return deleted_count
    
    def get_knowledge_stats(self, project_id: str) -> Dict[str, int]:
        collection = self._get_chunks_collection(project_id)
        
        pipeline = [
            {"$match": {}},
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
            return {"documentCount": 0, "chunkCount": 0, "embeddedChunks": 0}
        
        embedded_count = collection.count_documents({"embedding": {"$exists": True}})
        
        return {
            "documentCount": result[0].get("documentCount", 0),
            "chunkCount": result[0].get("chunkCount", 0),
            "embeddedChunks": embedded_count,
            "embeddingModel": "BAAI/bge-small-en-v1.5"
        }
    
    def get_knowledge_documents(self, project_id: str) -> List[Dict[str, Any]]:
        collection = self._get_docs_collection(project_id)
        
        documents = list(collection.find({}).sort("uploadedAt", -1))
        
        for doc in documents:
            if "id" not in doc and "_id" in doc:
                doc["id"] = str(doc["_id"])
            if "_id" in doc:
                del doc["_id"]
        
        return documents
    
    def create_knowledge_document(self, doc_data: Dict[str, Any]) -> Dict[str, Any]:
        import uuid
        from datetime import datetime
        
        project_id = doc_data.get("projectId", "global")
        collection = self._get_docs_collection(project_id)
        
        doc = {
            "id": str(uuid.uuid4()),
            "uploadedAt": datetime.utcnow().isoformat(),
            **doc_data
        }
        collection.insert_one(doc)
        if "_id" in doc:
            del doc["_id"]
        return doc
    
    def update_knowledge_document(self, document_id: str, project_id: str, updates: Dict[str, Any]) -> bool:
        collection = self._get_docs_collection(project_id)
        result = collection.update_one(
            {"id": document_id},
            {"$set": updates}
        )
        return result.modified_count > 0

    def delete_knowledge_document(self, document_id: str, project_id: str) -> bool:
        collection = self._get_docs_collection(project_id)
        
        doc = collection.find_one({"id": document_id})
        if not doc:
            log_info(f"Document {document_id} not found in project {project_id} collection", "kb")
            return False
        
        result = collection.delete_one({"id": document_id})
        deleted = result.deleted_count > 0
        
        if deleted:
            log_info(f"Successfully deleted document {document_id} from {self._docs_collection_name(project_id)}", "kb")
        else:
            log_error(f"Failed to delete document {document_id}", "kb", None)
        
        return deleted
    
    def delete_knowledge_document_complete(self, document_id: str, project_id: str) -> Dict[str, Any]:
        log_info(f"Starting complete deletion for document {document_id} in project {project_id}", "kb")
        
        chunks_deleted = self.delete_document_chunks(document_id, project_id)
        doc_deleted = self.delete_knowledge_document(document_id, project_id)
        
        result = {
            "documentId": document_id,
            "chunksDeleted": chunks_deleted,
            "documentDeleted": doc_deleted,
            "success": doc_deleted
        }
        
        if doc_deleted:
            log_info(f"Complete deletion successful for {document_id}: {chunks_deleted} chunks + 1 document removed", "kb")
        else:
            log_info(f"Document {document_id} not found, but cleaned up {chunks_deleted} orphaned chunks", "kb")
        
        return result
    
    def cleanup_orphaned_chunks(self, project_id: str) -> int:
        chunks_collection = self._get_chunks_collection(project_id)
        docs_collection = self._get_docs_collection(project_id)
        
        chunk_doc_ids = chunks_collection.distinct("documentId")
        valid_doc_ids = set(doc["id"] for doc in docs_collection.find({}, {"id": 1}))
        
        orphaned_ids = [doc_id for doc_id in chunk_doc_ids if doc_id not in valid_doc_ids]
        
        if not orphaned_ids:
            return 0
        
        total_deleted = 0
        for doc_id in orphaned_ids:
            result = chunks_collection.delete_many({"documentId": doc_id})
            total_deleted += result.deleted_count
        
        log_info(f"Cleanup complete: Removed {total_deleted} total orphaned chunks for project {project_id}", "kb")
        return total_deleted
    
    def verify_document_deletion(self, document_id: str, project_id: str) -> Dict[str, Any]:
        chunks_collection = self._get_chunks_collection(project_id)
        docs_collection = self._get_docs_collection(project_id)
        
        doc_exists = docs_collection.count_documents({"id": document_id}) > 0
        chunk_count = chunks_collection.count_documents({"documentId": document_id})
        
        is_clean = not doc_exists and chunk_count == 0
        
        return {
            "documentId": document_id,
            "documentExists": doc_exists,
            "remainingChunks": chunk_count,
            "isCompletelyDeleted": is_clean
        }
    
    def get_project_collection_info(self, project_id: str) -> Dict[str, Any]:
        chunks_name = self._chunks_collection_name(project_id)
        docs_name = self._docs_collection_name(project_id)
        
        chunks_col = self.db[chunks_name]
        docs_col = self.db[docs_name]
        
        chunks_indexes = list(chunks_col.list_indexes())
        docs_indexes = list(docs_col.list_indexes())
        
        total_chunks = chunks_col.count_documents({})
        embedded_count = chunks_col.count_documents({"embedding": {"$exists": True}})
        
        vector_search_indexes = []
        try:
            for idx in chunks_col.list_search_indexes():
                vector_search_indexes.append({
                    "name": idx.get("name"),
                    "type": idx.get("type"),
                    "status": idx.get("status"),
                    "queryable": idx.get("queryable"),
                    "definition": idx.get("latestDefinition")
                })
        except Exception:
            pass
        
        return {
            "projectId": project_id,
            "chunksCollection": chunks_name,
            "documentsCollection": docs_name,
            "chunksIndexes": [idx.get("name") for idx in chunks_indexes],
            "documentsIndexes": [idx.get("name") for idx in docs_indexes],
            "vectorSearchIndexes": vector_search_indexes,
            "chunksCount": total_chunks,
            "embeddedChunks": embedded_count,
            "documentsCount": docs_col.count_documents({}),
            "embeddingModel": "BAAI/bge-small-en-v1.5",
            "embeddingDimension": 384
        }
    
    def reingest_document(self, document_id: str, project_id: str) -> Dict[str, Any]:
        """Re-ingest an existing document with improved paragraph-based chunking."""
        chunks_col = self._get_chunks_collection(project_id)
        docs_col = self._get_docs_collection(project_id)
        
        doc_record = docs_col.find_one({"id": document_id})
        if not doc_record:
            return {"success": False, "error": "Document not found"}
        
        full_content = doc_record.get("rawContent", "")
        
        if not full_content:
            existing_chunks = list(chunks_col.find(
                {"documentId": document_id},
                {"content": 1, "chunkIndex": 1}
            ).sort("chunkIndex", 1))
            
            if not existing_chunks:
                return {"success": False, "error": "No existing chunks found"}
            
            full_content = "\n".join(c.get("content", "") for c in existing_chunks)
        
        old_count = chunks_col.count_documents({"documentId": document_id})
        
        filename = doc_record.get("filename", doc_record.get("originalName", "unknown"))
        
        chunks_col.delete_many({"documentId": document_id})
        
        chunk_count = self.ingest_document(document_id, project_id, filename, full_content)
        
        docs_col.update_one(
            {"id": document_id},
            {"$set": {"chunkCount": chunk_count, "status": "ready", "reingested": True}}
        )
        
        return {
            "success": True,
            "documentId": document_id,
            "filename": filename,
            "oldChunks": old_count,
            "newChunks": chunk_count
        }


def get_kb_service() -> KnowledgeBaseService:
    """Dependency for getting KB service."""
    return KnowledgeBaseService(get_db())
