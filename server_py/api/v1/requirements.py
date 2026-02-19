"""Requirements, BRD, test cases, test data, and user stories API router."""
import json
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from typing import Optional

from repositories import storage
from services import ai_service
from services.jira_service import jira_service
from services.knowledge_base_service import get_kb_service
from services.session_restore_service import (
    restore_feature_request, restore_brd, restore_analysis,
    restore_documentation, restore_database_schema,
    restore_test_cases, restore_user_stories, get_project_context
)
from schemas.requests_requirements import (
    GenerateUserStoriesRequest, GenerateBRDRequest,
    GenerateTestCasesRequest, GenerateTestDataRequest,
    GenerateCopilotPromptRequest
)
from core.logging import log_info, log_error
from utils.exceptions import bad_request, not_found, internal_error
from utils.response import success_response

router = APIRouter(tags=["requirements"])


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
    """Create a new feature request/requirement."""
    try:
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"

        final_description = description or ""

        if inputType == "audio" and audio:
            audio_buffer = await audio.read()
            final_description = await ai_service.transcribe_audio(audio_buffer)

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
    """Generate a Business Requirements Document (BRD) via SSE streaming."""
    try:
        feature_request = restore_feature_request(request.featureRequest)
        if not feature_request:
            raise bad_request("No feature request found")

        analysis = restore_analysis(request.analysis)
        documentation = restore_documentation(request.documentation)
        database_schema = restore_database_schema(request.databaseSchema)

        knowledge_context = None
        knowledge_sources = []
        try:
            # Construct focused search query based on feature request
            # Prioritize title and description, include request type for context
            request_type_context = {
                'feature': 'new feature functionality component',
                'bug': 'bug fix error issue problem',
                'enhancement': 'enhancement improvement optimization'
            }.get(feature_request.requestType, '')
            
            # Build comprehensive search query focused on user's request
            search_query = f"{feature_request.title} {feature_request.description} {request_type_context}"
            
            log_info(f"KB Search Query: {search_query[:150]}...", "requirements")
            
            # Retrieve relevant knowledge chunks (limit to top 5 most relevant)
            kb_results = get_kb_service().search_knowledge_base("global", search_query, 5)
            
            if kb_results:
                log_info(f"Retrieved {len(kb_results)} knowledge chunks with avg score: {sum(r.get('score', 0) for r in kb_results) / len(kb_results):.3f}", "requirements")
                
                # Format knowledge context with clear source attribution
                knowledge_context = "\n\n---\n\n".join([
                    f"[Source: {r['filename']} | Relevance: {r.get('score', 0):.2f}]\n{r['content']}" 
                    for r in kb_results
                ])
                
                knowledge_sources = [
                    {
                        "filename": r["filename"],
                        "chunkPreview": r["content"][:200] + ("..." if len(r["content"]) > 200 else ""),
                        "relevanceScore": r.get("score", 0)
                    }
                    for r in kb_results
                ]
            else:
                log_info("No relevant knowledge base content found for this feature request", "requirements")
                
        except Exception as kb_error:
            log_error("Knowledge base search error", "requirements", kb_error)

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
        brd = restore_brd(request.brdData)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        _, analysis, documentation, _ = get_project_context()

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
        brd = restore_brd(request.brd)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        documentation = restore_documentation(request.documentation)
        test_cases_list = restore_test_cases(request.testCases, brd.id)

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
        brd = restore_brd(request.brdData)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        _, _, documentation, database_schema = get_project_context()
        documentation = restore_documentation(request.documentation) if not documentation else documentation

        parent_context = None
        if request.parentJiraKey:
            parent_context = await jira_service.get_parent_story_context(request.parentJiraKey)

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
        brd = restore_brd(request.brd)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        user_stories_list = restore_user_stories(request.userStories, brd.id)
        if not user_stories_list:
            raise bad_request("No user stories found. Please generate user stories first.")

        _, analysis, documentation, database_schema = get_project_context()
        documentation_data = documentation.model_dump() if documentation else request.documentation
        analysis_data = analysis.model_dump() if analysis else request.analysis
        database_schema_data = database_schema.model_dump() if database_schema else request.databaseSchema

        feature_request_data = request.featureRequest
        if not feature_request_data:
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
