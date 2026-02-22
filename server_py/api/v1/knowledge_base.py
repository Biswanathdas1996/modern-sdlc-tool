"""Knowledge base API router."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from io import BytesIO
import json
import asyncio
import queue
import threading
from schemas import KnowledgeSearchRequest
from services.knowledge_base_service import get_kb_service
from core.logging import log_info, log_error
from utils.exceptions import bad_request, internal_error
from utils.response import success_response
from utils.doc_parsing import parse_document, ParsedContent
from utils.image_captioning import caption_document_images

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
    """Upload a document with multimodal processing and SSE streaming progress.
    
    Pipeline: Parse → Extract Images → Vision LLM Captioning → Chunk (text + captions) → Embed → Store
    """
    if not file:
        raise bad_request("No file provided")
    if not project_id:
        raise bad_request("project_id is required")
    
    file_content = await file.read()
    filename = file.filename or "unknown"
    content_type = file.content_type or "text/plain"
    
    async def event_stream():
        progress_queue = queue.Queue()
        
        def on_progress(step: str, detail: str):
            progress_queue.put({"step": step, "detail": detail})
        
        def send_sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"
        
        yield send_sse({"step": "upload", "detail": f"File '{filename}' received, starting multimodal processing..."})
        await asyncio.sleep(0)
        
        yield send_sse({"step": "parsing", "detail": f"Extracting text and images from '{filename}'..."})
        await asyncio.sleep(0)
        
        loop = asyncio.get_event_loop()
        parsed = await loop.run_in_executor(None, parse_document, file_content, content_type, filename)
        
        text_only = parsed.full_text
        image_count = len(parsed.images)
        text_block_count = len(parsed.text_blocks)
        
        parse_detail = f"Extracted {text_block_count} text blocks"
        if image_count > 0:
            parse_detail += f" and {image_count} images"
        if parsed.metadata.get("page_count"):
            parse_detail += f" from {parsed.metadata['page_count']} pages"
        elif parsed.metadata.get("slide_count"):
            parse_detail += f" from {parsed.metadata['slide_count']} slides"
        
        yield send_sse({"step": "parsing_done", "detail": parse_detail})
        await asyncio.sleep(0)
        
        if not text_only or len(text_only.strip()) < 50:
            if image_count == 0:
                yield send_sse({"step": "error", "detail": "File content too short or could not be extracted"})
                return
        
        captioned_count = 0
        if image_count > 0:
            yield send_sse({"step": "captioning", "detail": f"Captioning {image_count} images with Vision AI (gemini-2.5-flash)..."})
            await asyncio.sleep(0)
            
            caption_done = asyncio.Event()
            caption_error: List[Optional[str]] = [None]
            
            def sync_caption_progress(step: str, detail: str):
                progress_queue.put({"step": step, "detail": detail})
            
            async def run_captioning():
                nonlocal parsed
                try:
                    parsed = await caption_document_images(
                        parsed,
                        on_progress=sync_caption_progress,
                        max_concurrent=3,
                    )
                except Exception as e:
                    caption_error[0] = str(e)
                    log_error("Error during image captioning", "api", e)
                finally:
                    caption_done.set()
            
            caption_task = asyncio.create_task(run_captioning())
            
            while not caption_done.is_set():
                await asyncio.sleep(0.3)
                while not progress_queue.empty():
                    try:
                        msg = progress_queue.get_nowait()
                        yield send_sse(msg)
                        await asyncio.sleep(0)
                    except queue.Empty:
                        break
            
            await caption_task
            
            while not progress_queue.empty():
                try:
                    msg = progress_queue.get_nowait()
                    yield send_sse(msg)
                    await asyncio.sleep(0)
                except queue.Empty:
                    break
            
            if caption_error[0]:
                yield send_sse({"step": "captioning_warning", "detail": f"Image captioning partially failed: {caption_error[0][:100]}. Proceeding with text content..."})
                await asyncio.sleep(0)
            
            captioned_count = sum(1 for img in parsed.images if img.caption)
        
        combined_content = parsed.combined_text_with_captions if captioned_count > 0 else text_only
        
        if not combined_content or len(combined_content.strip()) < 50:
            yield send_sse({"step": "error", "detail": "Insufficient content extracted from document"})
            return
        
        kb_service = get_kb_service()
        doc = kb_service.create_knowledge_document({
            "projectId": project_id,
            "filename": filename,
            "originalName": filename,
            "contentType": content_type,
            "size": len(file_content),
            "imageCount": image_count,
            "captionedImageCount": captioned_count,
        })
        
        yield send_sse({"step": "document_created", "detail": f"Document record created (ID: {doc['id'][:8]}...)"})
        await asyncio.sleep(0)
        
        result = {"doc": doc, "error": None}
        
        def run_ingestion():
            try:
                chunk_count = kb_service.ingest_document(
                    doc["id"], project_id, filename, combined_content,
                    on_progress=on_progress,
                    image_count=image_count,
                    captioned_image_count=captioned_count,
                )
                update_data = {"chunkCount": chunk_count, "status": "ready"}
                if image_count > 0:
                    update_data["imageCount"] = image_count
                    update_data["captionedImageCount"] = captioned_count
                kb_service.update_knowledge_document(
                    doc["id"], project_id, update_data
                )
                result["doc"]["chunkCount"] = chunk_count
                result["doc"]["status"] = "ready"
            except Exception as e:
                log_error("Error ingesting document", "api", e)
                kb_service.update_knowledge_document(
                    doc["id"], project_id,
                    {"status": "error", "errorMessage": str(e)}
                )
                result["doc"]["status"] = "error"
                result["error"] = str(e)
            finally:
                progress_queue.put(None)
        
        thread = threading.Thread(target=run_ingestion, daemon=True)
        thread.start()
        
        while True:
            try:
                msg = progress_queue.get(timeout=0.3)
                if msg is None:
                    break
                yield send_sse(msg)
                await asyncio.sleep(0)
            except queue.Empty:
                continue
        
        thread.join(timeout=5)
        
        if result["error"]:
            yield send_sse({
                "step": "error",
                "detail": result["error"],
                "document": result["doc"]
            })
        else:
            img_note = f" ({captioned_count} image captions included)" if captioned_count > 0 else ""
            yield send_sse({
                "step": "done",
                "detail": f"'{filename}' is ready for semantic search{img_note}",
                "document": result["doc"]
            })
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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
