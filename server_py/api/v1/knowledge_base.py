"""Knowledge base API router."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Dict, Any
from io import BytesIO
import json
from schemas import KnowledgeSearchRequest
from services import get_kb_service
from core.database import get_db
from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error
from utils.response import success_response

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


@router.get("")
async def get_knowledge_documents():
    """Get all knowledge documents."""
    try:
        from mongodb_client import get_knowledge_documents_from_mongo
        documents = get_knowledge_documents_from_mongo()
        return documents
    except Exception as e:
        log_error("Error fetching knowledge documents", "api", e)
        raise internal_error("Failed to fetch knowledge documents")


@router.get("/stats")
async def get_knowledge_stats():
    """Get knowledge base statistics."""
    try:
        kb_service = get_kb_service()
        stats = kb_service.get_knowledge_stats("global")
        return stats
    except Exception as e:
        log_error("Error fetching knowledge stats", "api", e)
        raise internal_error("Failed to fetch knowledge stats")


@router.post("/upload", status_code=201)
async def upload_knowledge_document(file: UploadFile = File(...)):
    """Upload a document to the knowledge base."""
    try:
        if not file:
            raise bad_request("No file provided")
        
        project_id = "global"
        
        # Read file content
        file_content = await file.read()
        content = ""
        
        # Parse different file types
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
        
        # Create document record
        from mongodb_client import (
            create_knowledge_document_in_mongo,
            update_knowledge_document_in_mongo
        )
        
        doc = create_knowledge_document_in_mongo({
            "projectId": project_id,
            "filename": file.filename or "unknown",
            "originalName": file.filename or "unknown",
            "contentType": file.content_type or "text/plain",
            "size": len(file_content),
        })
        
        # Ingest document
        try:
            kb_service = get_kb_service()
            chunk_count = kb_service.ingest_document(
                doc["id"],
                project_id,
                doc["filename"],
                content
            )
            update_knowledge_document_in_mongo(
                doc["id"],
                {"chunkCount": chunk_count, "status": "ready"}
            )
            doc["chunkCount"] = chunk_count
            doc["status"] = "ready"
        except Exception as ingest_error:
            log_error("Error ingesting document", "api", ingest_error)
            update_knowledge_document_in_mongo(
                doc["id"],
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
async def delete_knowledge_document(id: str):
    """Delete a knowledge document."""
    try:
        from mongodb_client import delete_knowledge_document_from_mongo
        
        kb_service = get_kb_service()
        kb_service.delete_document_chunks(id)
        
        deleted = delete_knowledge_document_from_mongo(id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return success_response(message="Document deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error deleting knowledge document", "api", e)
        raise internal_error("Failed to delete knowledge document")


@router.post("/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    """Search the knowledge base."""
    try:
        kb_service = get_kb_service()
        results = kb_service.search_knowledge_base(
            "global",
            request.query,
            request.limit
        )
        return results
    except Exception as e:
        log_error("Error searching knowledge base", "api", e)
        raise internal_error("Failed to search knowledge base")
