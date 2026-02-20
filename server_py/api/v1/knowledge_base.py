"""Knowledge base API router."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from typing import List, Dict, Any, Optional
from io import BytesIO
import json
from schemas import KnowledgeSearchRequest
from services.knowledge_base_service import get_kb_service
from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error
from utils.response import success_response

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


@router.get("")
async def get_knowledge_documents(project_id: Optional[str] = Query(None)):
    """Get all knowledge documents for a project."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        kb_service = get_kb_service()
        documents = kb_service.get_knowledge_documents(project_id)
        return documents
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching knowledge documents", "api", e)
        raise internal_error("Failed to fetch knowledge documents")


@router.get("/stats")
async def get_knowledge_stats(project_id: Optional[str] = Query(None)):
    """Get knowledge base statistics for a project."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        kb_service = get_kb_service()
        stats = kb_service.get_knowledge_stats(project_id)
        return stats
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching knowledge stats", "api", e)
        raise internal_error("Failed to fetch knowledge stats")


@router.get("/collection-info")
async def get_collection_info(project_id: str = Query(...)):
    """Get MongoDB collection info and indexes for a project."""
    try:
        kb_service = get_kb_service()
        info = kb_service.get_project_collection_info(project_id)
        return success_response(data=info)
    except Exception as e:
        log_error("Error fetching collection info", "api", e)
        raise internal_error("Failed to fetch collection info")


@router.post("/upload", status_code=201)
async def upload_knowledge_document(file: UploadFile = File(...), project_id: Optional[str] = Form(None)):
    """Upload a document to the project-specific knowledge base collection."""
    try:
        if not file:
            raise bad_request("No file provided")
        
        if not project_id:
            raise bad_request("project_id is required")
        
        file_content = await file.read()
        content = ""
        
        try:
            if file.content_type in ["text/plain", "text/markdown", "text/csv"]:
                content = file_content.decode("utf-8", errors="ignore")
            elif file.content_type == "application/json":
                json_content = json.loads(file_content.decode("utf-8"))
                content = json.dumps(json_content, indent=2)
            elif file.content_type == "application/pdf":
                from PyPDF2 import PdfReader
                reader = PdfReader(BytesIO(file_content))
                content = "\n".join([
                    page.extract_text() or "" 
                    for page in reader.pages
                ])
            elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                from docx import Document
                doc = Document(BytesIO(file_content))
                content = "\n".join([para.text for para in doc.paragraphs])
            else:
                content = file_content.decode("utf-8", errors="ignore")
        except Exception as parse_error:
            log_error("Error parsing file", "api", parse_error)
            content = file_content.decode("utf-8", errors="ignore")
        
        if not content or len(content.strip()) < 50:
            raise bad_request(
                "File content too short or could not be extracted"
            )
        
        kb_service = get_kb_service()
        doc = kb_service.create_knowledge_document({
            "projectId": project_id,
            "filename": file.filename or "unknown",
            "originalName": file.filename or "unknown",
            "contentType": file.content_type or "text/plain",
            "size": len(file_content),
        })
        
        try:
            kb_service = get_kb_service()
            chunk_count = kb_service.ingest_document(
                doc["id"],
                project_id,
                doc["filename"],
                content
            )
            kb_service.update_knowledge_document(
                doc["id"],
                project_id,
                {"chunkCount": chunk_count, "status": "ready"}
            )
            doc["chunkCount"] = chunk_count
            doc["status"] = "ready"
        except Exception as ingest_error:
            log_error("Error ingesting document", "api", ingest_error)
            kb_service.update_knowledge_document(
                doc["id"],
                project_id,
                {"status": "error", "errorMessage": str(ingest_error)}
            )
            doc["status"] = "error"
            doc["errorMessage"] = str(ingest_error)
        
        return doc
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error uploading knowledge document", "api", e)
        raise internal_error("Failed to upload knowledge document")


@router.delete("/{id}")
async def delete_knowledge_document(id: str, project_id: Optional[str] = Query(None)):
    """Delete a knowledge document completely from its project collection."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        
        kb_service = get_kb_service()
        
        result = kb_service.delete_knowledge_document_complete(id, project_id)
        
        if not result["success"]:
            raise HTTPException(status_code=404, detail="Document not found")
        
        log_info(f"Document deletion completed: {result['chunksDeleted']} chunks + 1 document removed from project {project_id}", "api")
        
        return success_response(
            message=f"Document deleted successfully. Removed {result['chunksDeleted']} chunks and 1 document.",
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error deleting knowledge document", "api", e)
        raise internal_error("Failed to delete knowledge document")


@router.post("/cleanup-orphaned")
async def cleanup_orphaned_chunks(project_id: Optional[str] = Query(None)):
    """Clean up orphaned chunks from a project's collection."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        
        kb_service = get_kb_service()
        deleted_count = kb_service.cleanup_orphaned_chunks(project_id)
        
        return success_response(
            message=f"Cleanup completed. Removed {deleted_count} orphaned chunks.",
            data={"orphanedChunksDeleted": deleted_count}
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error cleaning up orphaned chunks", "api", e)
        raise internal_error("Failed to cleanup orphaned chunks")


@router.get("/verify-deletion/{id}")
async def verify_document_deletion(id: str, project_id: Optional[str] = Query(None)):
    """Verify that a document is completely deleted from its project collection."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        
        kb_service = get_kb_service()
        result = kb_service.verify_document_deletion(id, project_id)
        
        if result["isCompletelyDeleted"]:
            message = f"Document {id} is completely deleted"
        else:
            message = f"Document {id} still has data: {result['remainingChunks']} chunks, document exists: {result['documentExists']}"
        
        return success_response(message=message, data=result)
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error verifying document deletion", "api", e)
        raise internal_error("Failed to verify document deletion")


@router.post("/reingest/{id}")
async def reingest_document(id: str, project_id: Optional[str] = Query(None)):
    """Re-ingest an existing document with improved chunking and embeddings."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        
        kb_service = get_kb_service()
        result = kb_service.reingest_document(id, project_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Document not found"))
        
        return success_response(
            message=f"Document re-ingested: {result['oldChunks']} old chunks replaced with {result['newChunks']} new chunks with improved chunking.",
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error re-ingesting document", "api", e)
        raise internal_error("Failed to re-ingest document")


@router.post("/reingest-all")
async def reingest_all_documents(project_id: Optional[str] = Query(None)):
    """Re-ingest all documents in a project with improved chunking and embeddings."""
    try:
        if not project_id:
            raise bad_request("project_id is required")
        
        kb_service = get_kb_service()
        documents = kb_service.get_knowledge_documents(project_id)
        
        if not documents:
            return success_response(message="No documents to re-ingest.", data={"count": 0})
        
        results = []
        for doc in documents:
            doc_id = doc.get("id")
            if doc_id:
                result = kb_service.reingest_document(doc_id, project_id)
                results.append(result)
        
        success_count = sum(1 for r in results if r.get("success"))
        return success_response(
            message=f"Re-ingested {success_count}/{len(documents)} documents with improved chunking.",
            data={"results": results, "totalProcessed": len(documents), "successful": success_count}
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error re-ingesting all documents", "api", e)
        raise internal_error("Failed to re-ingest documents")


@router.post("/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    """Search the knowledge base within a project's collection."""
    try:
        if not request.project_id:
            raise bad_request("project_id is required")
        
        kb_service = get_kb_service()
        results = kb_service.search_knowledge_base(
            request.project_id,
            request.query,
            request.limit
        )
        return results
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error searching knowledge base", "api", e)
        raise internal_error("Failed to search knowledge base")
