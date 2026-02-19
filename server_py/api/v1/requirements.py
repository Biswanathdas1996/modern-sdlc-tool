"""Requirements, BRD, test cases, test data, and user stories API router."""
import os
import json
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from repositories import storage
from services import ai_service
from services.jira_service import jira_service
from services.knowledge_base_service import get_kb_service
from core.logging import log_info, log_error
from utils.exceptions import bad_request, not_found, internal_error
from utils.response import success_response

router = APIRouter(tags=["requirements"])


# ==================== REQUEST/RESPONSE MODELS ====================

class GenerateUserStoriesRequest(BaseModel):
    """Request for generating user stories."""
    brdData: Optional[dict] = None
    documentation: Optional[dict] = None
    parentJiraKey: Optional[str] = None


class UpdateUserStoryRequest(BaseModel):
    """Request for updating a user story."""
    pass  # Accepts any fields


class GenerateBRDRequest(BaseModel):
    """Request for generating BRD."""
    featureRequest: Optional[dict] = None
    analysis: Optional[dict] = None
    databaseSchema: Optional[dict] = None
    documentation: Optional[dict] = None


class GenerateTestCasesRequest(BaseModel):
    """Request for generating test cases."""
    brdData: Optional[dict] = None


class GenerateTestDataRequest(BaseModel):
    """Request for generating test data."""
    brd: Optional[dict] = None
    documentation: Optional[dict] = None
    testCases: Optional[List[dict]] = None


class GenerateCopilotPromptRequest(BaseModel):
    """Request for generating GitHub Copilot prompt."""
    brd: Optional[dict] = None
    userStories: Optional[List[dict]] = None
    documentation: Optional[dict] = None
    analysis: Optional[dict] = None
    databaseSchema: Optional[dict] = None
    featureRequest: Optional[dict] = None


# ==================== REQUIREMENTS ENDPOINTS ====================

@router.post("/requirements")
async def create_requirements(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    inputType: str = Form(...),
    requestType: str = Form("feature"),
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None)
):
    """
    Create a new feature request/requirement.
    
    Supports text, file upload, or audio transcription input.
    """
    try:
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"
        
        final_description = description or ""
        
        # Handle audio input
        if inputType == "audio" and audio:
            audio_buffer = await audio.read()
            final_description = await ai_service.transcribe_audio(audio_buffer)
        
        # Handle file input
        if inputType == "file" and file:
            file_content = await file.read()
            final_description = file_content.decode("utf-8", errors="ignore")
        
        feature_request = storage.create_feature_request({
            "projectId": project_id,
            "title": title,
            "description": final_description,
            "inputType": inputType,
            "requestType": requestType,
            "rawInput": final_description,
        })
        
        log_info(f"Feature request created: {title}", "requirements")
        return JSONResponse(status_code=201, content=feature_request.model_dump())
        
    except Exception as e:
        log_error("Error creating feature request", "requirements", e)
        raise internal_error("Failed to create feature request")


# ==================== BRD ENDPOINTS ====================

@router.get("/brd/current")
async def get_current_brd():
    """Get the current BRD."""
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise not_found("No BRD found")
        
        return brd.model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error fetching BRD", "requirements", e)
        raise internal_error("Failed to fetch BRD")


@router.post("/brd/generate")
async def generate_brd_endpoint(request: GenerateBRDRequest):
    """
    Generate a Business Requirements Document (BRD).
    
    Streams the generation progress using Server-Sent Events (SSE).
    """
    try:
        # Get or restore feature request
        feature_request = storage.get_current_feature_request()
        if not feature_request and request.featureRequest:
            from schemas.entities import FeatureRequest as FRModel
            fr_data = request.featureRequest
            feature_request = FRModel(
                id=fr_data.get("id", "restored"),
                projectId=fr_data.get("projectId", "global"),
                title=fr_data.get("title", ""),
                description=fr_data.get("description", ""),
                inputType=fr_data.get("inputType", "text"),
                requestType=fr_data.get("requestType", "feature"),
                createdAt=fr_data.get("createdAt", datetime.now().isoformat()),
            )
            storage.feature_requests[feature_request.id] = feature_request
            storage.current_feature_request_id = feature_request.id
        
        if not feature_request:
            raise bad_request("No feature request found")
        
        # Get context data
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"
        
        analysis = storage.get_analysis(project_id) if projects else None
        documentation = storage.get_documentation(project_id) if projects else None
        database_schema = storage.get_database_schema(project_id) if projects else None
        
        # Restore from request if not in storage
        if not analysis and request.analysis:
            from schemas.entities import RepoAnalysis
            analysis = RepoAnalysis(**request.analysis)
        if not database_schema and request.databaseSchema:
            from schemas.entities import DatabaseSchemaInfo as DatabaseSchema
            database_schema = DatabaseSchema(**request.databaseSchema)
        if not documentation and request.documentation:
            from schemas.entities import Documentation
            documentation = Documentation(**request.documentation)
        
        # Get knowledge base context
        knowledge_context = None
        knowledge_sources = []
        try:
            search_query = f"{feature_request.title} {feature_request.description}"
            kb_results = get_kb_service().search_knowledge_base("global", search_query, 5)
            if kb_results:
                knowledge_context = "\n\n---\n\n".join([
                    f"[Source: {r['filename']}]\n{r['content']}" for r in kb_results
                ])
                knowledge_sources = [
                    {
                        "filename": r["filename"],
                        "chunkPreview": r["content"][:200] + ("..." if len(r["content"]) > 200 else "")
                    }
                    for r in kb_results
                ]
        except Exception as kb_error:
            log_error("Knowledge base search error", "requirements", kb_error)
        
        # Stream BRD generation
        async def generate():
            try:
                if knowledge_sources:
                    yield {"data": json.dumps({"knowledgeSources": knowledge_sources})}
                
                brd = await ai_service.generate_brd(
                    feature_request.model_dump(),
                    analysis.model_dump() if analysis else None,
                    documentation.model_dump() if documentation else None,
                    database_schema.model_dump() if database_schema else None,
                    knowledge_context,
                    lambda chunk: None
                )
                
                brd["knowledgeSources"] = knowledge_sources if knowledge_sources else None
                storage.create_brd(brd)
                
                yield {"data": json.dumps({"content": json.dumps(brd.get("content", {}))})}
                yield {"data": json.dumps({"done": True})}
            except Exception as gen_error:
                log_error("BRD generation error", "requirements", gen_error)
                yield {"data": json.dumps({"error": "Generation failed"})}
        
        return EventSourceResponse(generate())
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error generating BRD", "requirements", e)
        raise internal_error("Failed to generate BRD")


# ==================== TEST CASES ENDPOINTS ====================

@router.get("/test-cases")
async def get_test_cases():
    """Get all test cases for the current BRD."""
    try:
        brd = storage.get_current_brd()
        if not brd:
            return []
        
        test_cases = storage.get_test_cases(brd.id)
        return [tc.model_dump() for tc in test_cases]
        
    except Exception as e:
        log_error("Error fetching test cases", "requirements", e)
        raise internal_error("Failed to fetch test cases")


@router.post("/test-cases/generate")
async def generate_test_cases_endpoint(request: GenerateTestCasesRequest):
    """Generate test cases from BRD."""
    try:
        brd = storage.get_current_brd()
        
        # Restore BRD from request if needed
        if not brd and request.brdData:
            from schemas.entities import BRD, BRDContent
            brd_data = request.brdData
            content = brd_data.get("content", {})
            brd_content = BRDContent(**content) if isinstance(content, dict) else content
            
            brd = BRD(
                id=brd_data.get("id", "restored"),
                projectId=brd_data.get("projectId", ""),
                featureRequestId=brd_data.get("featureRequestId", ""),
                requestType=brd_data.get("requestType", "feature"),
                title=brd_data.get("title", ""),
                version=brd_data.get("version", "1.0"),
                status=brd_data.get("status", "draft"),
                content=brd_content,
                knowledgeSources=brd_data.get("knowledgeSources", []),
                createdAt=brd_data.get("createdAt", datetime.now().isoformat()),
                updatedAt=brd_data.get("updatedAt", datetime.now().isoformat()),
            )
            storage.brds[brd.id] = brd
            storage.current_brd_id = brd.id
        
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")
        
        projects = storage.get_all_projects()
        analysis = storage.get_analysis(projects[0].id) if projects else None
        documentation = storage.get_documentation(projects[0].id) if projects else None
        
        test_cases = await ai_service.generate_test_cases(
            brd.model_dump(),
            analysis.model_dump() if analysis else None,
            documentation.model_dump() if documentation else None
        )
        
        if not test_cases:
            raise internal_error("Failed to generate test cases - no cases returned")
        
        saved_test_cases = storage.create_test_cases(test_cases)
        log_info(f"Generated {len(saved_test_cases)} test cases", "requirements")
        
        return [tc.model_dump() for tc in saved_test_cases]
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error generating test cases", "requirements", e)
        raise internal_error("Failed to generate test cases")


# ==================== TEST DATA ENDPOINTS ====================

@router.get("/test-data")
async def get_test_data():
    """Get all test data."""
    try:
        test_data = storage.get_all_test_data()
        return [td.model_dump() for td in test_data]
        
    except Exception as e:
        log_error("Error fetching test data", "requirements", e)
        raise internal_error("Failed to fetch test data")


@router.post("/test-data/generate")
async def generate_test_data_endpoint(request: GenerateTestDataRequest):
    """Generate test data from test cases."""
    try:
        brd = storage.get_current_brd()
        
        # Restore BRD from request if needed
        if not brd and request.brd:
            from schemas.entities import BRD
            brd = BRD(**request.brd)
            storage.brds[brd.id] = brd
        
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")
        
        # Get or restore documentation
        documentation = None
        projects = storage.get_all_projects()
        if projects:
            documentation = storage.get_documentation(projects[0].id)
        if not documentation and request.documentation:
            from schemas import Documentation
            documentation = Documentation(**request.documentation)
        
        # Get or restore test cases
        test_cases_list = storage.get_test_cases(brd.id)
        if not test_cases_list and request.testCases:
            from schemas.entities import TestCase
            for tc_data in request.testCases:
                tc = TestCase(**tc_data)
                storage.test_cases[tc.id] = tc
            test_cases_list = list(storage.test_cases.values())
        
        if not test_cases_list:
            raise bad_request("No test cases found. Please generate test cases first.")
        
        test_data = await ai_service.generate_test_data(
            [tc.model_dump() for tc in test_cases_list],
            brd.model_dump(),
            documentation.model_dump() if documentation else None
        )
        
        if not test_data:
            raise internal_error("Failed to generate test data - no data returned")
        
        saved_test_data = storage.create_test_data_batch(test_data)
        log_info(f"Generated {len(saved_test_data)} test data entries", "requirements")
        
        return [td.model_dump() for td in saved_test_data]
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error generating test data", "requirements", e)
        raise internal_error("Failed to generate test data")


# ==================== USER STORIES ENDPOINTS ====================

@router.get("/user-stories/{brd_id}")
async def get_user_stories(brd_id: str):
    """Get all user stories for a BRD."""
    try:
        user_stories = storage.get_user_stories(brd_id)
        return [s.model_dump() for s in user_stories]
        
    except Exception as e:
        log_error("Error fetching user stories", "requirements", e)
        raise internal_error("Failed to fetch user stories")


@router.post("/user-stories/generate")
async def generate_user_stories_endpoint(request: GenerateUserStoriesRequest):
    """Generate user stories from BRD."""
    try:
        brd = storage.get_current_brd()
        
        # Restore BRD from request if needed
        if not brd and request.brdData:
            from schemas.entities import BRD, BRDContent
            brd_data = request.brdData
            content = brd_data.get("content", {})
            brd_content = BRDContent(**content) if isinstance(content, dict) else content
            
            brd = BRD(
                id=brd_data.get("id", "restored"),
                projectId=brd_data.get("projectId", ""),
                featureRequestId=brd_data.get("featureRequestId", ""),
                requestType=brd_data.get("requestType", "feature"),
                title=brd_data.get("title", ""),
                version=brd_data.get("version", "1.0"),
                status=brd_data.get("status", "draft"),
                content=brd_content,
                knowledgeSources=brd_data.get("knowledgeSources", []),
                createdAt=brd_data.get("createdAt", datetime.now().isoformat()),
                updatedAt=brd_data.get("updatedAt", datetime.now().isoformat()),
            )
            storage.brds[brd.id] = brd
            storage.current_brd_id = brd.id
        
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")
        
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"
        documentation = storage.get_documentation(project_id) if projects else None
        database_schema = storage.get_database_schema(project_id) if projects else None
        
        # Restore documentation from request if needed
        if not documentation and request.documentation:
            from schemas.entities import Documentation
            documentation = Documentation(**request.documentation)
        
        # Get parent JIRA context if provided
        parent_context = None
        if request.parentJiraKey:
            parent_context = await jira_service.get_parent_story_context(request.parentJiraKey)
        
        # Get knowledge base context
        knowledge_context = None
        try:
            search_query = f"{brd.title} {brd.content.overview if hasattr(brd.content, 'overview') else ''}"
            kb_results = get_kb_service().search_knowledge_base("global", search_query, 5)
            if kb_results:
                knowledge_context = "\n\n---\n\n".join([
                    f"[Source: {r['filename']}]\n{r['content']}" for r in kb_results
                ])
        except Exception as kb_error:
            log_error("Knowledge base search error", "requirements", kb_error)
        
        user_stories = await ai_service.generate_user_stories(
            brd.model_dump(),
            documentation.model_dump() if documentation else None,
            database_schema.model_dump() if database_schema else None,
            parent_context,
            knowledge_context
        )
        
        if not user_stories:
            raise internal_error("Failed to generate user stories - no stories returned")
        
        # Add parent JIRA key if provided
        stories_with_parent = [
            {**story, "parentJiraKey": request.parentJiraKey}
            for story in user_stories
        ]
        
        saved_stories = storage.create_user_stories(stories_with_parent)
        log_info(f"Generated {len(saved_stories)} user stories", "requirements")
        
        return [s.model_dump() for s in saved_stories]
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error generating user stories", "requirements", e)
        raise internal_error("Failed to generate user stories")


@router.patch("/user-stories/{id}")
async def update_user_story(id: str, updates: dict):
    """Update a user story."""
    try:
        updated_story = storage.update_user_story(id, updates)
        if not updated_story:
            raise not_found("User story not found")
        
        log_info(f"User story updated: {id}", "requirements")
        return updated_story.model_dump()
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error updating user story", "requirements", e)
        raise internal_error("Failed to update user story")


@router.delete("/user-stories/{id}")
async def delete_user_story(id: str):
    """Delete a user story."""
    try:
        deleted = storage.delete_user_story(id)
        if not deleted:
            raise not_found("User story not found")
        
        log_info(f"User story deleted: {id}", "requirements")
        return success_response(message="User story deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error deleting user story", "requirements", e)
        raise internal_error("Failed to delete user story")


# ==================== COPILOT PROMPT ENDPOINT ====================

@router.post("/copilot-prompt/generate")
async def generate_copilot_prompt_endpoint(request: GenerateCopilotPromptRequest):
    """Generate a GitHub Copilot prompt from user stories and context."""
    try:
        brd = storage.get_current_brd()
        
        # Restore BRD from request if needed
        if not brd and request.brd:
            from schemas.entities import BRD
            brd = BRD(**request.brd)
            storage.brds[brd.id] = brd
        
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")
        
        # Get or restore user stories
        user_stories_list = storage.get_user_stories(brd.id)
        if not user_stories_list and request.userStories:
            from schemas.entities import UserStory
            for us_data in request.userStories:
                story = UserStory(**us_data)
                storage.user_stories[story.id] = story
            user_stories_list = storage.get_user_stories(brd.id)
        
        if not user_stories_list:
            raise bad_request("No user stories found. Please generate user stories first.")
        
        # Get context
        projects = storage.get_all_projects()
        documentation = storage.get_documentation(projects[0].id) if projects else None
        analysis = storage.get_analysis(projects[0].id) if projects else None
        database_schema = storage.get_database_schema(projects[0].id) if projects else None
        
        # Use provided data if storage is empty
        documentation_data = documentation.model_dump() if documentation else request.documentation
        analysis_data = analysis.model_dump() if analysis else request.analysis
        database_schema_data = database_schema.model_dump() if database_schema else request.databaseSchema
        
        # Get feature request
        feature_request_data = None
        if request.featureRequest:
            feature_request_data = request.featureRequest
        else:
            fr = storage.get_current_feature_request()
            if fr:
                feature_request_data = fr.model_dump()
        
        prompt = await ai_service.generate_copilot_prompt(
            [s.model_dump() for s in user_stories_list],
            documentation_data,
            analysis_data,
            database_schema_data,
            feature_request_data
        )
        
        log_info("Copilot prompt generated", "requirements")
        return {"prompt": prompt}
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("Error generating Copilot prompt", "requirements", e)
        raise internal_error("Failed to generate Copilot prompt")
