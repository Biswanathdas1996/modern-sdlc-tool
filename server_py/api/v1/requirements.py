"""Requirements, BRD, test cases, test data, and user stories API router."""
import json
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Query
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
    project_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None)
):
    """Create a new feature request/requirement."""
    try:
        if not project_id:
            projects = storage.get_all_projects()
            if not projects:
                raise not_found("No projects found. Create a project first.")
            project_id = projects[0]["id"]

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
        return JSONResponse(status_code=201, content=feature_request)

    except Exception as e:
        log_error("Error creating feature request", "requirements", e)
        raise internal_error("Failed to create feature request")


# ==================== BRD ENDPOINTS ====================

@router.get("/brd/current")
async def get_current_brd(project_id: Optional[str] = Query(None)):
    """Get the current BRD, optionally scoped to a project."""
    try:
        brd = storage.get_current_brd(project_id=project_id)
        if not brd:
            raise not_found("No BRD found")
        return brd
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
            request_type_context = {
                'feature': 'new feature functionality component',
                'bug': 'bug fix error issue problem',
                'enhancement': 'enhancement improvement optimization'
            }.get(feature_request.get("requestType", "feature"), '')
            
            search_query = f"{feature_request['title']} {feature_request['description']} {request_type_context}"
            
            log_info(f"KB Search Query: {search_query[:150]}...", "requirements")
            
            kb_project_id = feature_request.get("projectId", "global")
            kb_results = get_kb_service().search_knowledge_base(kb_project_id, search_query, 5)
            
            if kb_results:
                log_info(f"Retrieved {len(kb_results)} knowledge chunks with avg score: {sum(r.get('score', 0) for r in kb_results) / len(kb_results):.3f}", "requirements")
                
                knowledge_context = "\n\n---\n\n".join([
                    f"[Source: {r['filename']} | Relevance: {r.get('score', 0):.2f}]\n{r['content']}" 
                    for r in kb_results
                ])
                
                knowledge_sources = [
                    {
                        "filename": r["filename"],
                        "chunkPreview": r["content"],
                        "relevanceScore": r.get("score", 0)
                    }
                    for r in kb_results
                ]
            else:
                log_info("No knowledge chunks met similarity threshold — KB context excluded from BRD generation", "requirements")
                
        except Exception as kb_error:
            log_error("Knowledge base search error", "requirements", kb_error)

        async def generate():
            try:
                if knowledge_sources:
                    yield {"data": json.dumps({"knowledgeSources": knowledge_sources})}

                brd = await ai_service.generate_brd(
                    feature_request,
                    analysis,
                    documentation,
                    database_schema,
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
async def get_test_cases(project_id: Optional[str] = Query(None)):
    """Get all test cases, optionally scoped to a project."""
    try:
        if project_id:
            return storage.get_test_cases_by_project(project_id)
        brd = storage.get_current_brd()
        if not brd:
            return []
        test_cases = storage.get_test_cases(brd["id"])
        return test_cases
    except Exception as e:
        log_error("Error fetching test cases", "requirements", e)
        raise internal_error("Failed to fetch test cases")


@router.post("/test-cases/generate")
async def generate_test_cases_endpoint(request: GenerateTestCasesRequest):
    """Generate test cases from BRD."""
    try:
        brd = None
        if request.brdId:
            brd = storage.brds_repo.get_by_id(request.brdId)
        if not brd:
            brd = restore_brd(request.brdData)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        brd_project_id = brd.get("projectId")
        _, analysis, documentation, _ = get_project_context(brd_project_id)

        test_cases = await ai_service.generate_test_cases(
            brd,
            analysis,
            documentation
        )

        if not test_cases:
            raise internal_error("Failed to generate test cases - no cases returned")

        for tc in test_cases:
            tc["projectId"] = brd_project_id

        saved_test_cases = storage.create_test_cases(test_cases)
        log_info(f"Generated {len(saved_test_cases)} test cases", "requirements")
        return saved_test_cases

    except HTTPException:
        raise
    except Exception as e:
        log_error("Error generating test cases", "requirements", e)
        raise internal_error("Failed to generate test cases")


# ==================== TEST DATA ENDPOINTS ====================

@router.get("/test-data")
async def get_test_data(project_id: Optional[str] = Query(None)):
    """Get all test data, optionally scoped to a project."""
    try:
        if project_id:
            return storage.get_test_data_by_project(project_id)
        test_data = storage.get_all_test_data()
        return test_data
    except Exception as e:
        log_error("Error fetching test data", "requirements", e)
        raise internal_error("Failed to fetch test data")


@router.post("/test-data/generate")
async def generate_test_data_endpoint(request: GenerateTestDataRequest):
    """Generate test data from test cases."""
    try:
        brd = None
        if request.brdId:
            brd = storage.brds_repo.get_by_id(request.brdId)
        if not brd:
            brd = restore_brd(request.brd)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        documentation = restore_documentation(request.documentation)
        test_cases_list = restore_test_cases(request.testCases, brd["id"])

        if not test_cases_list:
            raise bad_request("No test cases found. Please generate test cases first.")

        brd_project_id = brd.get("projectId")

        test_data = await ai_service.generate_test_data(
            test_cases_list,
            brd,
            documentation
        )

        if not test_data:
            raise internal_error("Failed to generate test data - no data returned")

        for td in test_data:
            td["projectId"] = brd_project_id

        saved_test_data = storage.create_test_data_batch(test_data)
        log_info(f"Generated {len(saved_test_data)} test data entries", "requirements")
        return saved_test_data

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
        return user_stories
    except Exception as e:
        log_error("Error fetching user stories", "requirements", e)
        raise internal_error("Failed to fetch user stories")


@router.post("/user-stories/generate")
async def generate_user_stories_endpoint(request: GenerateUserStoriesRequest):
    """Generate user stories from BRD."""
    try:
        brd = None
        if request.brdId:
            brd = storage.brds_repo.get_by_id(request.brdId)
        if not brd:
            brd = restore_brd(request.brdData)
        if not brd:
            raise bad_request("No BRD found. Please generate a BRD first.")

        brd_project_id = brd.get("projectId")
        _, _, documentation, database_schema = get_project_context(brd_project_id)
        documentation = restore_documentation(request.documentation) if not documentation else documentation

        parent_context = None
        if request.parentJiraKey:
            parent_context = await jira_service.get_parent_story_context(request.parentJiraKey)

        knowledge_context = None
        try:
            search_query = f"{brd['title']} {brd.get('content', {}).get('overview', '')}"
            kb_project_id = brd.get("projectId", "global")
            kb_results = get_kb_service().search_knowledge_base(kb_project_id, search_query, 5)
            if kb_results:
                knowledge_context = "\n\n---\n\n".join([
                    f"[Source: {r['filename']}]\n{r['content']}" for r in kb_results
                ])
        except Exception as kb_error:
            log_error("Knowledge base search error", "requirements", kb_error)

        user_stories = await ai_service.generate_user_stories(
            brd,
            documentation,
            database_schema,
            parent_context,
            knowledge_context
        )

        if not user_stories:
            raise internal_error("Failed to generate user stories - no stories returned")

        stories_with_parent = [
            {**story, "parentJiraKey": request.parentJiraKey, "projectId": brd_project_id}
            for story in user_stories
        ]

        saved_stories = storage.create_user_stories(stories_with_parent)
        log_info(f"Generated {len(saved_stories)} user stories", "requirements")
        return saved_stories

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
        return updated_story
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

        user_stories_list = restore_user_stories(request.userStories, brd["id"])
        if not user_stories_list:
            raise bad_request("No user stories found. Please generate user stories first.")

        brd_project_id = brd.get("projectId")
        _, analysis, documentation, database_schema = get_project_context(brd_project_id)
        documentation_data = documentation if documentation else request.documentation
        analysis_data = analysis if analysis else request.analysis
        database_schema_data = database_schema if database_schema else request.databaseSchema

        feature_request_data = request.featureRequest
        if not feature_request_data:
            fr = storage.get_current_feature_request()
            if fr:
                feature_request_data = fr

        prompt = await ai_service.generate_copilot_prompt(
            user_stories_list,
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


# ==================== GENERATION HISTORY ====================

@router.get("/generation-history")
async def get_generation_history(project_id: str = Query(...)):
    """Get all generated artifacts grouped by feature request for a project."""
    try:
        feature_requests = storage.get_feature_requests_by_project(project_id)
        brds = storage.get_brds_by_project(project_id)
        test_cases = storage.get_test_cases_by_project(project_id)
        test_data = storage.get_test_data_by_project(project_id)
        user_stories = storage.get_user_stories_by_project(project_id)

        brds_by_fr = {}
        for brd in brds:
            fr_id = brd.get("featureRequestId", "")
            brds_by_fr.setdefault(fr_id, []).append(brd)

        stories_by_brd = {}
        for story in user_stories:
            brd_id = story.get("brdId", "")
            stories_by_brd.setdefault(brd_id, []).append(story)

        cases_by_brd = {}
        for tc in test_cases:
            brd_id = tc.get("brdId", "")
            cases_by_brd.setdefault(brd_id, []).append(tc)

        data_by_tc = {}
        for td in test_data:
            tc_id = td.get("testCaseId", "")
            data_by_tc.setdefault(tc_id, []).append(td)

        grouped = []
        for fr in feature_requests:
            fr_id = fr["id"]
            fr_brds = brds_by_fr.get(fr_id, [])

            brd_items = []
            for brd in fr_brds:
                brd_id = brd["id"]
                brd_stories = stories_by_brd.get(brd_id, [])
                brd_cases = cases_by_brd.get(brd_id, [])

                brd_test_data = []
                for tc in brd_cases:
                    brd_test_data.extend(data_by_tc.get(tc["id"], []))

                brd_items.append({
                    "id": brd["id"],
                    "title": brd.get("title", ""),
                    "version": brd.get("version", "1.0"),
                    "status": brd.get("status", "draft"),
                    "createdAt": brd.get("createdAt", ""),
                    "userStoryCount": len(brd_stories),
                    "testCaseCount": len(brd_cases),
                    "testDataCount": len(brd_test_data),
                    "userStories": brd_stories,
                    "testCases": brd_cases,
                    "testData": brd_test_data,
                })

            total_brds = len(brd_items)
            total_stories = sum(b["userStoryCount"] for b in brd_items)
            total_cases = sum(b["testCaseCount"] for b in brd_items)
            total_data = sum(b["testDataCount"] for b in brd_items)

            grouped.append({
                "featureRequest": {
                    "id": fr["id"],
                    "title": fr.get("title", ""),
                    "description": fr.get("description", ""),
                    "requestType": fr.get("requestType", "feature"),
                    "createdAt": fr.get("createdAt", ""),
                },
                "summary": {
                    "brdCount": total_brds,
                    "userStoryCount": total_stories,
                    "testCaseCount": total_cases,
                    "testDataCount": total_data,
                },
                "brds": brd_items,
            })

        grouped.sort(key=lambda x: x["featureRequest"].get("createdAt", ""), reverse=True)

        log_info(f"Generation history: {len(grouped)} feature requests for project {project_id}", "requirements")
        return grouped

    except Exception as e:
        log_error("Error fetching generation history", "requirements", e)
        raise internal_error("Failed to fetch generation history")


@router.delete("/feature-request/{feature_request_id}")
async def delete_feature_request(feature_request_id: str):
    """Delete a feature request and all its cascading artifacts (BRDs, user stories, test cases, test data)."""
    try:
        fr = storage.get_feature_request(feature_request_id)
        if not fr:
            raise not_found("Feature request not found")

        brds = storage.get_brds_by_project(fr["projectId"])
        fr_brds = [b for b in brds if b.get("featureRequestId") == feature_request_id]

        all_test_cases = storage.get_test_cases_by_project(fr["projectId"])
        for brd in fr_brds:
            brd_id = brd["id"]
            brd_cases = [tc for tc in all_test_cases if tc.get("brdId") == brd_id]
            for tc in brd_cases:
                storage.test_data_repo.delete_by_field("testCaseId", tc["id"])
            storage.test_cases_repo.delete_by_field("brdId", brd_id)
            storage.user_stories_repo.delete_by_field("brdId", brd_id)
            storage.brds_repo.delete(brd_id)

        storage.feature_requests_repo.delete(feature_request_id)

        log_info(f"Deleted feature request {feature_request_id} and {len(fr_brds)} BRDs", "requirements")
        return success_response({"deleted": True, "featureRequestId": feature_request_id})

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error deleting feature request {feature_request_id}", "requirements", e)
        raise internal_error("Failed to delete feature request")
