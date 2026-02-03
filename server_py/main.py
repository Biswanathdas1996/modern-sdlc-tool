import os
import re
import json
import base64
import asyncio
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse
import httpx

from storage import storage
from models import AnalyzeRequest, RequirementsRequest
from ai import (
    analyze_repository, generate_documentation, generate_bpmn_diagram,
    generate_brd, generate_test_cases, generate_test_data,
    generate_user_stories, generate_copilot_prompt, find_related_stories,
    transcribe_audio
)
from mongodb_client import (
    ingest_document, search_knowledge_base, delete_document_chunks,
    get_knowledge_stats, create_knowledge_document_in_mongo,
    get_knowledge_documents_from_mongo, update_knowledge_document_in_mongo,
    delete_knowledge_document_from_mongo
)

app = FastAPI(title="DocuGen AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def log(message: str, source: str = "express"):
    formatted_time = datetime.now().strftime("%I:%M:%S %p")
    print(f"{formatted_time} [{source}] {message}")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start).total_seconds() * 1000
    
    if request.url.path.startswith("/api"):
        log(f"{request.method} {request.url.path} {response.status_code} in {duration:.0f}ms")
    
    return response


@app.get("/api/projects")
async def get_projects():
    try:
        projects = storage.get_all_projects()
        return [p.model_dump() for p in projects]
    except Exception as e:
        print(f"Error fetching projects: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch projects")


@app.get("/api/projects/{id}")
async def get_project(id: str):
    try:
        project = storage.get_project(id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching project: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@app.delete("/api/projects/{id}")
async def delete_project(id: str):
    try:
        project = storage.get_project(id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        storage.delete_project(id)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting project: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete project")


async def run_analysis(project_id: str, repo_url: str):
    try:
        analysis = await analyze_repository(repo_url, project_id)
        storage.create_analysis(analysis)
        
        tech_stack = []
        if analysis.get("techStack"):
            tech_stack = analysis["techStack"].get("languages", []) + analysis["techStack"].get("frameworks", [])
        
        storage.update_project(project_id, {
            "techStack": tech_stack,
            "description": analysis.get("summary", ""),
        })
        
        try:
            updated_project = storage.get_project(project_id)
            if updated_project:
                documentation = await generate_documentation(analysis, updated_project.model_dump())
                saved_doc = storage.create_documentation(documentation)
                
                try:
                    print("Generating BPMN diagrams for features...")
                    bpmn_data = await generate_bpmn_diagram(saved_doc.model_dump(), analysis)
                    storage.create_bpmn_diagram(bpmn_data)
                    print("BPMN diagrams generated successfully")
                except Exception as bpmn_error:
                    print(f"BPMN diagram generation error: {bpmn_error}")
        except Exception as doc_error:
            print(f"Documentation generation error: {doc_error}")
        
        storage.update_project(project_id, {"status": "completed"})
    except Exception as error:
        print(f"Analysis error: {error}")
        storage.update_project(project_id, {"status": "error"})


@app.post("/api/projects/analyze")
async def analyze_project(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    try:
        repo_url = request.repoUrl
        
        match = re.match(r"github\.com/([^/]+)/([^/]+)", repo_url.replace("https://", ""))
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub URL")
        
        repo_name = f"{match.group(1)}/{match.group(2)}".replace(".git", "")
        
        project = storage.create_project({
            "name": repo_name,
            "repoUrl": repo_url,
            "techStack": [],
            "status": "analyzing",
        })
        
        background_tasks.add_task(run_analysis, project.id, repo_url)
        
        return JSONResponse(status_code=201, content=project.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error analyzing repository: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze repository")


@app.get("/api/analysis/current")
async def get_current_analysis():
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise HTTPException(status_code=404, detail="No projects found")
        analysis = storage.get_analysis(projects[0].id)
        if not analysis:
            raise HTTPException(status_code=404, detail="No analysis found")
        return analysis.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis")


@app.get("/api/documentation/current")
async def get_current_documentation():
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise HTTPException(status_code=404, detail="No projects found")
        doc = storage.get_documentation(projects[0].id)
        if not doc:
            raise HTTPException(status_code=404, detail="No documentation found")
        return doc.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching documentation: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch documentation")


@app.get("/api/bpmn/current")
async def get_current_bpmn():
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise HTTPException(status_code=404, detail="No projects found")
        doc = storage.get_documentation(projects[0].id)
        if not doc:
            raise HTTPException(status_code=404, detail="No documentation found")
        bpmn = storage.get_bpmn_diagram(doc.id)
        if not bpmn:
            raise HTTPException(status_code=404, detail="No BPMN diagrams found")
        return bpmn.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching BPMN diagrams: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch BPMN diagrams")


@app.post("/api/bpmn/regenerate")
async def regenerate_bpmn():
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise HTTPException(status_code=404, detail="No projects found")
        project = projects[0]
        doc = storage.get_documentation(project.id)
        if not doc:
            raise HTTPException(status_code=404, detail="No documentation found")
        analysis = storage.get_analysis(project.id)
        if not analysis:
            raise HTTPException(status_code=404, detail="No analysis found")
        
        storage.delete_bpmn_diagram(doc.id)
        bpmn_data = await generate_bpmn_diagram(doc.model_dump(), analysis.model_dump())
        new_bpmn = storage.create_bpmn_diagram(bpmn_data)
        
        return new_bpmn.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error regenerating BPMN diagram: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate BPMN diagram")


@app.post("/api/database-schema/connect")
async def connect_database_schema(request: Request):
    try:
        import psycopg2
        
        body = await request.json()
        connection_string = body.get("connectionString", "").strip()
        
        if not connection_string:
            raise HTTPException(status_code=400, detail="Connection string is required")
        
        if connection_string.lower().startswith("psql "):
            connection_string = connection_string[5:].strip()
        if (connection_string.startswith("'") and connection_string.endswith("'")) or \
           (connection_string.startswith('"') and connection_string.endswith('"')):
            connection_string = connection_string[1:-1]
        
        projects = storage.get_all_projects()
        if not projects:
            raise HTTPException(status_code=400, detail="Please analyze a repository first")
        project = projects[0]
        
        try:
            conn = psycopg2.connect(connection_string)
            cursor = conn.cursor()
            
            cursor.execute("SELECT current_database()")
            database_name = cursor.fetchone()[0]
            
            query = """
                SELECT 
                    t.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
                    CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_foreign_key,
                    fk.foreign_table_name || '.' || fk.foreign_column_name as references_column
                FROM information_schema.tables t
                JOIN information_schema.columns c ON t.table_name = c.table_name AND t.table_schema = c.table_schema
                LEFT JOIN (
                    SELECT ku.table_name, ku.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
                ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
                LEFT JOIN (
                    SELECT 
                        kcu.table_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
                ) fk ON c.table_name = fk.table_name AND c.column_name = fk.column_name
                WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name, c.ordinal_position
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            tables_map = {}
            for row in rows:
                table_name = row[0]
                if table_name not in tables_map:
                    tables_map[table_name] = []
                tables_map[table_name].append({
                    "name": row[1],
                    "dataType": row[2],
                    "isNullable": row[3] == "YES",
                    "defaultValue": row[4],
                    "isPrimaryKey": row[5],
                    "isForeignKey": row[6],
                    "references": row[7],
                })
            
            tables = []
            for table_name, columns in tables_map.items():
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                row_count = cursor.fetchone()[0]
                tables.append({
                    "name": table_name,
                    "columns": columns,
                    "rowCount": row_count,
                })
            
            cursor.close()
            conn.close()
            
            storage.delete_database_schema(project.id)
            
            masked_connection_string = re.sub(r"(://[^:]+:)[^@]+(@)", r"\1****\2", connection_string)
            
            schema_info = storage.create_database_schema({
                "projectId": project.id,
                "connectionString": masked_connection_string,
                "databaseName": database_name,
                "tables": tables,
            })
            
            documentation = storage.get_documentation(project.id)
            if documentation:
                storage.update_documentation(project.id, {
                    "databaseSchema": {
                        "databaseName": database_name,
                        "connectionString": masked_connection_string,
                        "tables": tables,
                    },
                })
                print(f"Database schema saved to documentation for project {project.id}")
            
            return schema_info.model_dump()
        except Exception as db_error:
            print(f"Database connection error: {db_error}")
            raise HTTPException(status_code=400, detail=f"Failed to connect to database: {str(db_error)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing database schema: {e}")
        raise HTTPException(status_code=500, detail="Failed to process database schema")


@app.get("/api/database-schema/current")
async def get_current_database_schema():
    try:
        projects = storage.get_all_projects()
        if not projects:
            return None
        schema = storage.get_database_schema(projects[0].id)
        return schema.model_dump() if schema else None
    except Exception as e:
        print(f"Error fetching database schema: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch database schema")


@app.delete("/api/database-schema/current")
async def delete_current_database_schema():
    try:
        projects = storage.get_all_projects()
        if not projects:
            raise HTTPException(status_code=404, detail="No project found")
        project = projects[0]
        storage.delete_database_schema(project.id)
        
        documentation = storage.get_documentation(project.id)
        if documentation:
            storage.update_documentation(project.id, {"databaseSchema": None})
            print(f"Database schema removed from documentation for project {project.id}")
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting database schema: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete database schema")


@app.post("/api/requirements")
async def create_requirements(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    inputType: str = Form(...),
    requestType: str = Form("feature"),
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None)
):
    try:
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"
        
        final_description = description or ""
        
        if inputType == "audio" and audio:
            audio_buffer = await audio.read()
            final_description = await transcribe_audio(audio_buffer)
        
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
        
        return JSONResponse(status_code=201, content=feature_request.model_dump())
    except Exception as e:
        print(f"Error creating feature request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create feature request")


@app.get("/api/brd/current")
async def get_current_brd():
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=404, detail="No BRD found")
        return brd.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching BRD: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch BRD")


@app.post("/api/brd/generate")
async def generate_brd_endpoint(request: Request):
    try:
        feature_request = storage.get_current_feature_request()
        if not feature_request:
            raise HTTPException(status_code=400, detail="No feature request found")
        
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"
        
        analysis = storage.get_analysis(project_id) if projects else None
        documentation = storage.get_documentation(project_id) if projects else None
        database_schema = storage.get_database_schema(project_id) if projects else None
        
        knowledge_context = None
        knowledge_sources = []
        try:
            search_query = f"{feature_request.title} {feature_request.description}"
            kb_results = search_knowledge_base("global", search_query, 5)
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
            print(f"Knowledge base search error: {kb_error}")
        
        print(f"Generating BRD with context: Documentation={documentation is not None}, Analysis={analysis is not None}, DB Schema={database_schema is not None}, Knowledge Base={knowledge_context is not None} ({len(knowledge_sources)} chunks)")
        
        async def generate():
            try:
                if knowledge_sources:
                    yield {"data": json.dumps({"knowledgeSources": knowledge_sources})}
                
                brd = await generate_brd(
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
                print(f"BRD generation error: {gen_error}")
                yield {"data": json.dumps({"error": "Generation failed"})}
        
        return EventSourceResponse(generate())
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating BRD: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate BRD")


@app.get("/api/test-cases")
async def get_test_cases():
    try:
        brd = storage.get_current_brd()
        if not brd:
            return []
        test_cases = storage.get_test_cases(brd.id)
        return [tc.model_dump() for tc in test_cases]
    except Exception as e:
        print(f"Error fetching test cases: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch test cases")


@app.post("/api/test-cases/generate")
async def generate_test_cases_endpoint():
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found. Please generate a BRD first.")
        
        projects = storage.get_all_projects()
        analysis = storage.get_analysis(projects[0].id) if projects else None
        documentation = storage.get_documentation(projects[0].id) if projects else None
        
        test_cases = await generate_test_cases(
            brd.model_dump(),
            analysis.model_dump() if analysis else None,
            documentation.model_dump() if documentation else None
        )
        
        if not test_cases:
            raise HTTPException(status_code=500, detail="Failed to generate test cases - no cases returned")
        
        saved_test_cases = storage.create_test_cases(test_cases)
        return [tc.model_dump() for tc in saved_test_cases]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating test cases: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate test cases")


@app.get("/api/test-data")
async def get_test_data():
    try:
        test_data = storage.get_all_test_data()
        return [td.model_dump() for td in test_data]
    except Exception as e:
        print(f"Error fetching test data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch test data")


@app.post("/api/test-data/generate")
async def generate_test_data_endpoint():
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found. Please generate a BRD first.")
        
        test_cases = storage.get_test_cases(brd.id)
        if not test_cases:
            raise HTTPException(status_code=400, detail="No test cases found. Please generate test cases first.")
        
        projects = storage.get_all_projects()
        documentation = storage.get_documentation(projects[0].id) if projects else None
        
        test_data = await generate_test_data(
            [tc.model_dump() for tc in test_cases],
            brd.model_dump(),
            documentation.model_dump() if documentation else None
        )
        
        if not test_data:
            raise HTTPException(status_code=500, detail="Failed to generate test data - no data returned")
        
        saved_test_data = storage.create_test_data_batch(test_data)
        return [td.model_dump() for td in saved_test_data]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating test data: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate test data")


@app.get("/api/user-stories/{brd_id}")
async def get_user_stories(brd_id: str):
    try:
        user_stories = storage.get_user_stories(brd_id)
        return [s.model_dump() for s in user_stories]
    except Exception as e:
        print(f"Error fetching user stories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user stories")


@app.post("/api/user-stories/generate")
async def generate_user_stories_endpoint(request: Request):
    try:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        parent_jira_key = body.get("parentJiraKey")
        
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found. Please generate a BRD first.")
        
        projects = storage.get_all_projects()
        project_id = projects[0].id if projects else "global"
        documentation = storage.get_documentation(project_id) if projects else None
        database_schema = storage.get_database_schema(project_id) if projects else None
        
        parent_context = None
        if parent_jira_key:
            try:
                jira_email = os.environ.get("JIRA_EMAIL")
                jira_token = os.environ.get("JIRA_API_TOKEN")
                jira_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
                
                if jira_email and jira_token:
                    auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            f"https://{jira_instance_url}/rest/api/3/issue/{parent_jira_key}?fields=summary,description",
                            headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
                        )
                        if response.status_code == 200:
                            issue = response.json()
                            desc_text = extract_text_from_adf(issue.get("fields", {}).get("description"))
                            parent_context = f"Parent Story [{parent_jira_key}]: {issue.get('fields', {}).get('summary', '')}"
                            if desc_text:
                                parent_context += f"\n\nDescription: {desc_text}"
            except Exception as err:
                print(f"Error fetching parent JIRA story: {err}")
        
        knowledge_context = None
        try:
            search_query = f"{brd.title} {brd.content.overview if hasattr(brd.content, 'overview') else ''}"
            kb_results = search_knowledge_base("global", search_query, 5)
            if kb_results:
                knowledge_context = "\n\n---\n\n".join([
                    f"[Source: {r['filename']}]\n{r['content']}" for r in kb_results
                ])
        except Exception as kb_error:
            print(f"Knowledge base search error: {kb_error}")
        
        user_stories = await generate_user_stories(
            brd.model_dump(),
            documentation.model_dump() if documentation else None,
            database_schema.model_dump() if database_schema else None,
            parent_context,
            knowledge_context
        )
        
        if not user_stories:
            raise HTTPException(status_code=500, detail="Failed to generate user stories - no stories returned")
        
        stories_with_parent = [
            {**story, "parentJiraKey": parent_jira_key}
            for story in user_stories
        ]
        
        saved_stories = storage.create_user_stories(stories_with_parent)
        return [s.model_dump() for s in saved_stories]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating user stories: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate user stories")


@app.patch("/api/user-stories/{id}")
async def update_user_story(id: str, request: Request):
    try:
        updates = await request.json()
        updated_story = storage.update_user_story(id, updates)
        if not updated_story:
            raise HTTPException(status_code=404, detail="User story not found")
        return updated_story.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating user story: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user story")


@app.delete("/api/user-stories/{id}")
async def delete_user_story(id: str):
    try:
        deleted = storage.delete_user_story(id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User story not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting user story: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user story")


@app.post("/api/copilot-prompt/generate")
async def generate_copilot_prompt_endpoint():
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found. Please generate a BRD first.")
        
        user_stories = storage.get_user_stories(brd.id)
        if not user_stories:
            raise HTTPException(status_code=400, detail="No user stories found. Please generate user stories first.")
        
        projects = storage.get_all_projects()
        documentation = storage.get_documentation(projects[0].id) if projects else None
        analysis = storage.get_analysis(projects[0].id) if projects else None
        database_schema = storage.get_database_schema(projects[0].id) if projects else None
        
        prompt = await generate_copilot_prompt(
            [s.model_dump() for s in user_stories],
            documentation.model_dump() if documentation else None,
            analysis.model_dump() if analysis else None,
            database_schema.model_dump() if database_schema else None
        )
        
        return {"prompt": prompt}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating Copilot prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate Copilot prompt")


def extract_text_from_adf(adf: Any) -> str:
    if not adf:
        return ""
    if isinstance(adf, str):
        return adf
    
    text_parts = []
    
    def extract(node: Any):
        if isinstance(node, dict):
            if node.get("type") == "text":
                text_parts.append(node.get("text", ""))
            for key in ["content", "children"]:
                if key in node:
                    for child in node[key]:
                        extract(child)
        elif isinstance(node, list):
            for item in node:
                extract(item)
    
    extract(adf)
    return " ".join(text_parts)


@app.post("/api/jira/sync")
async def sync_to_jira():
    try:
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        jira_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
        jira_project_key = os.environ.get("JIRA_PROJECT_KEY", "KAN")
        
        if not jira_email or not jira_token:
            raise HTTPException(status_code=400, detail="JIRA credentials not configured. Please add JIRA_EMAIL and JIRA_API_TOKEN secrets.")
        
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found. Please generate a BRD first.")
        
        user_stories = storage.get_user_stories(brd.id)
        if not user_stories:
            raise HTTPException(status_code=400, detail="No user stories found. Please generate user stories first.")
        
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        jira_base_url = f"https://{jira_instance_url}/rest/api/3"
        
        results = []
        
        async with httpx.AsyncClient() as client:
            for story in user_stories:
                try:
                    description = {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": f"As a {story.asA}, I want {story.iWant}, so that {story.soThat}"}
                                ]
                            },
                            {
                                "type": "heading",
                                "attrs": {"level": 3},
                                "content": [{"type": "text", "text": "Acceptance Criteria"}]
                            },
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": criteria}]}]
                                    }
                                    for criteria in story.acceptanceCriteria
                                ]
                            }
                        ]
                    }
                    
                    if story.description:
                        description["content"].insert(1, {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": story.description}]
                        })
                    
                    if story.technicalNotes:
                        description["content"].extend([
                            {
                                "type": "heading",
                                "attrs": {"level": 3},
                                "content": [{"type": "text", "text": "Technical Notes"}]
                            },
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": story.technicalNotes}]
                            }
                        ])
                    
                    is_subtask = bool(story.parentJiraKey)
                    issue_type_name = "Sub-task" if is_subtask else "Story"
                    
                    issue_data = {
                        "fields": {
                            "project": {"key": jira_project_key},
                            "summary": story.title,
                            "description": description,
                            "issuetype": {"name": issue_type_name},
                            "labels": story.labels or []
                        }
                    }
                    
                    if is_subtask and story.parentJiraKey:
                        issue_data["fields"]["parent"] = {"key": story.parentJiraKey}
                    
                    response = await client.post(
                        f"{jira_base_url}/issue",
                        headers={
                            "Authorization": f"Basic {auth}",
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                        },
                        json=issue_data
                    )
                    
                    if response.status_code == 201:
                        data = response.json()
                        result_info = {"storyKey": story.storyKey, "jiraKey": data.get("key")}
                        if is_subtask:
                            result_info["parentKey"] = story.parentJiraKey
                            result_info["isSubtask"] = True
                        results.append(result_info)
                    else:
                        print(f"JIRA API error for {story.storyKey}: {response.text}")
                        results.append({"storyKey": story.storyKey, "error": f"Failed to create issue: {response.status_code}"})
                except Exception as err:
                    print(f"Error syncing story {story.storyKey}: {err}")
                    results.append({"storyKey": story.storyKey, "error": str(err)})
        
        success_count = len([r for r in results if r.get("jiraKey")])
        fail_count = len([r for r in results if r.get("error")])
        
        return {
            "message": f"Synced {success_count} stories to JIRA. {f'{fail_count} failed.' if fail_count > 0 else ''}",
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error syncing to JIRA: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync to JIRA")


@app.get("/api/jira/stories")
async def get_jira_stories():
    try:
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        jira_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
        jira_project_key = os.environ.get("JIRA_PROJECT_KEY", "KAN")
        
        if not jira_email or not jira_token:
            raise HTTPException(status_code=400, detail="JIRA credentials not configured.")
        
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        jira_base_url = f"https://{jira_instance_url}/rest/api/3"
        
        jql = f"project = {jira_project_key} AND issuetype = Story ORDER BY created DESC"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{jira_base_url}/search/jql",
                params={"jql": jql, "fields": "summary,description,status,priority,labels,subtasks"},
                headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
            )
            
            if response.status_code != 200:
                print(f"JIRA API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch JIRA stories")
            
            data = response.json()
            stories = [
                {
                    "key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "description": extract_text_from_adf(issue.get("fields", {}).get("description")),
                    "status": issue.get("fields", {}).get("status", {}).get("name", "Unknown"),
                    "priority": issue.get("fields", {}).get("priority", {}).get("name", "Medium"),
                    "labels": issue.get("fields", {}).get("labels", []),
                    "subtaskCount": len(issue.get("fields", {}).get("subtasks", []))
                }
                for issue in data.get("issues", [])
            ]
            
            return stories
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching JIRA stories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch JIRA stories")


@app.post("/api/jira/find-related")
async def find_related_jira_stories(request: Request):
    try:
        body = await request.json()
        feature_description = body.get("featureDescription")
        if not feature_description:
            raise HTTPException(status_code=400, detail="Feature description is required")
        
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        jira_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
        jira_project_key = os.environ.get("JIRA_PROJECT_KEY", "KAN")
        
        if not jira_email or not jira_token:
            return {"relatedStories": []}
        
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        jira_base_url = f"https://{jira_instance_url}/rest/api/3"
        
        jql = f"project = {jira_project_key} ORDER BY created DESC"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{jira_base_url}/search/jql",
                params={"jql": jql, "fields": "summary,description,status,priority,labels,issuetype", "maxResults": 100},
                headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
            )
            
            if response.status_code != 200:
                return {"relatedStories": []}
            
            data = response.json()
            jira_stories = [
                {
                    "key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "description": extract_text_from_adf(issue.get("fields", {}).get("description")),
                    "status": issue.get("fields", {}).get("status", {}).get("name", "Unknown"),
                    "priority": issue.get("fields", {}).get("priority", {}).get("name", "Medium"),
                    "labels": issue.get("fields", {}).get("labels", []),
                    "issueType": issue.get("fields", {}).get("issuetype", {}).get("name", "Unknown")
                }
                for issue in data.get("issues", [])
            ]
            
            if not jira_stories:
                return {"relatedStories": []}
            
            related_stories = await find_related_stories(feature_description, jira_stories)
            return {"relatedStories": related_stories}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error finding related stories: {e}")
        raise HTTPException(status_code=500, detail="Failed to find related stories")


@app.post("/api/jira/sync-subtask")
async def sync_subtask_to_jira(request: Request):
    try:
        body = await request.json()
        story_id = body.get("storyId")
        parent_key = body.get("parentKey")
        
        if not story_id or not parent_key:
            raise HTTPException(status_code=400, detail="Story ID and parent JIRA key are required")
        
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        jira_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
        jira_project_key = os.environ.get("JIRA_PROJECT_KEY", "KAN")
        
        if not jira_email or not jira_token:
            raise HTTPException(status_code=400, detail="JIRA credentials not configured.")
        
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found")
        
        user_stories = storage.get_user_stories(brd.id)
        story = next((s for s in user_stories if s.id == story_id), None)
        
        if not story:
            raise HTTPException(status_code=404, detail="User story not found")
        
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        jira_base_url = f"https://{jira_instance_url}/rest/api/3"
        
        description = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"As a {story.asA}, I want {story.iWant}, so that {story.soThat}"}]
                },
                {
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": "Acceptance Criteria"}]
                },
                {
                    "type": "bulletList",
                    "content": [
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": criteria}]}]}
                        for criteria in story.acceptanceCriteria
                    ]
                }
            ]
        }
        
        issue_data = {
            "fields": {
                "project": {"key": jira_project_key},
                "parent": {"key": parent_key},
                "summary": story.title,
                "description": description,
                "issuetype": {"name": "Subtask"},
                "labels": story.labels or []
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{jira_base_url}/issue",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                json=issue_data
            )
            
            if response.status_code == 201:
                data = response.json()
                storage.update_user_story(story_id, {"parentJiraKey": parent_key, "jiraKey": data.get("key")})
                return {
                    "storyKey": story.storyKey,
                    "jiraKey": data.get("key"),
                    "parentKey": parent_key,
                    "message": f"Created subtask {data.get('key')} under {parent_key}"
                }
            else:
                print(f"JIRA API error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail=f"Failed to create subtask: {response.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating JIRA subtask: {e}")
        raise HTTPException(status_code=500, detail="Failed to create JIRA subtask")


@app.post("/api/confluence/publish")
async def publish_to_confluence(request: Request):
    try:
        body = await request.json()
        brd_id = body.get("brdId")
        
        jira_email = os.environ.get("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        confluence_instance_url = os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net")
        confluence_space_key = os.environ.get("CONFLUENCE_SPACE_KEY", "~5caf6d452c573b4b24d0f933")
        
        if not jira_email or not jira_token:
            raise HTTPException(status_code=400, detail="Confluence credentials not configured.")
        
        brd = storage.get_brd(brd_id) if brd_id else storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found. Please generate a BRD first.")
        
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        confluence_base_url = f"https://{confluence_instance_url}/wiki/api/v2"
        
        adf_content = build_confluence_content(brd.model_dump())
        
        async with httpx.AsyncClient() as client:
            space_response = await client.get(
                f"https://{confluence_instance_url}/wiki/api/v2/spaces",
                params={"keys": confluence_space_key},
                headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
            )
            
            space_id = confluence_space_key
            if space_response.status_code == 200:
                space_data = space_response.json()
                if space_data.get("results"):
                    space_id = space_data["results"][0].get("id", confluence_space_key)
            
            create_page_body = {
                "spaceId": space_id,
                "status": "current",
                "title": f"BRD: {brd.title} - {datetime.now().strftime('%Y-%m-%d')}",
                "body": {
                    "representation": "atlas_doc_format",
                    "value": json.dumps(adf_content)
                }
            }
            
            response = await client.post(
                f"{confluence_base_url}/pages",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                json=create_page_body
            )
            
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                page_id = data.get("id", "")
                webui_link = data.get("_links", {}).get("webui", "")
                if webui_link:
                    page_url = f"https://{confluence_instance_url}/wiki{webui_link}"
                else:
                    page_url = f"https://{confluence_instance_url}/wiki/spaces/{confluence_space_key}/pages/{page_id}"
                return {
                    "success": True,
                    "pageId": page_id,
                    "pageUrl": page_url,
                    "message": "BRD published to Confluence successfully"
                }
            else:
                print(f"Confluence API error ({response.status_code}): {response.text}")
                raise HTTPException(status_code=response.status_code, detail=f"Failed to publish to Confluence: {response.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error publishing to Confluence: {e}")
        raise HTTPException(status_code=500, detail="Failed to publish to Confluence")


def build_confluence_content(brd: Dict[str, Any]) -> Dict[str, Any]:
    content = brd.get("content", {})
    
    def create_bullet_list(items: List[str]) -> Dict[str, Any]:
        if not items:
            return {"type": "paragraph", "content": [{"type": "text", "text": "None specified"}]}
        return {
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": item or "N/A"}]}]}
                for item in items
            ]
        }
    
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": brd.get("title", "")}]},
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Overview"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": content.get("overview", "No overview provided")}]},
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Objectives"}]},
            create_bullet_list(content.get("objectives", [])),
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Scope"}]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "In Scope"}]},
            create_bullet_list(content.get("scope", {}).get("inScope", [])),
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Out of Scope"}]},
            create_bullet_list(content.get("scope", {}).get("outOfScope", [])),
            {"type": "rule"},
            {"type": "paragraph", "content": [{"type": "text", "text": f"Generated by DocuGen AI | Version: {brd.get('version', '1.0')} | Status: {brd.get('status', 'draft')}", "marks": [{"type": "em"}]}]}
        ]
    }


@app.get("/api/knowledge-base")
async def get_knowledge_base():
    try:
        documents = get_knowledge_documents_from_mongo()
        return documents
    except Exception as e:
        print(f"Error fetching knowledge documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch knowledge documents")


@app.get("/api/knowledge-base/stats")
async def get_knowledge_base_stats():
    try:
        stats = get_knowledge_stats("global")
        return stats
    except Exception as e:
        print(f"Error fetching knowledge stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch knowledge stats")


@app.post("/api/knowledge-base/upload")
async def upload_knowledge_document(file: UploadFile = File(...)):
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")
        
        project_id = "global"
        
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
                content = "\n".join([page.extract_text() or "" for page in reader.pages])
            elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                from docx import Document
                doc = Document(BytesIO(file_content))
                content = "\n".join([para.text for para in doc.paragraphs])
            else:
                content = file_content.decode("utf-8", errors="ignore")
        except Exception as parse_error:
            print(f"Error parsing file: {parse_error}")
            content = file_content.decode("utf-8", errors="ignore")
        
        if not content or len(content.strip()) < 50:
            raise HTTPException(status_code=400, detail="File content too short or could not be extracted")
        
        doc = create_knowledge_document_in_mongo({
            "projectId": project_id,
            "filename": file.filename or "unknown",
            "originalName": file.filename or "unknown",
            "contentType": file.content_type or "text/plain",
            "size": len(file_content),
        })
        
        try:
            chunk_count = ingest_document(doc["id"], project_id, doc["filename"], content)
            update_knowledge_document_in_mongo(doc["id"], {"chunkCount": chunk_count, "status": "ready"})
            doc["chunkCount"] = chunk_count
            doc["status"] = "ready"
        except Exception as ingest_error:
            print(f"Error ingesting document: {ingest_error}")
            update_knowledge_document_in_mongo(doc["id"], {"status": "error", "errorMessage": str(ingest_error)})
            doc["status"] = "error"
            doc["errorMessage"] = str(ingest_error)
        
        return JSONResponse(status_code=201, content=doc)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading knowledge document: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload knowledge document")


@app.delete("/api/knowledge-base/{id}")
async def delete_knowledge_document(id: str):
    try:
        delete_document_chunks(id)
        deleted = delete_knowledge_document_from_mongo(id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting knowledge document: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete knowledge document")


@app.post("/api/knowledge-base/search")
async def search_knowledge(request: Request):
    try:
        body = await request.json()
        query = body.get("query", "")
        limit = body.get("limit", 5)
        
        results = search_knowledge_base("global", query, limit)
        return results
    except Exception as e:
        print(f"Error searching knowledge base: {e}")
        raise HTTPException(status_code=500, detail="Failed to search knowledge base")


VITE_DEV_SERVER = "http://localhost:5173"


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_to_vite(request: Request, path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    if os.environ.get("NODE_ENV") == "production":
        try:
            static_path = f"../client/dist/{path}" if path else "../client/dist/index.html"
            if os.path.exists(static_path):
                with open(static_path, "rb") as f:
                    content = f.read()
                content_type = "text/html"
                if path.endswith(".js"):
                    content_type = "application/javascript"
                elif path.endswith(".css"):
                    content_type = "text/css"
                elif path.endswith(".json"):
                    content_type = "application/json"
                return Response(content=content, media_type=content_type)
            else:
                with open("../client/dist/index.html", "rb") as f:
                    content = f.read()
                return Response(content=content, media_type="text/html")
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")
    else:
        try:
            async with httpx.AsyncClient() as client:
                url = f"{VITE_DEV_SERVER}/{path}"
                if request.query_params:
                    url += f"?{request.query_params}"
                
                response = await client.request(
                    method=request.method,
                    url=url,
                    headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]},
                    content=await request.body() if request.method in ["POST", "PUT", "PATCH"] else None,
                    timeout=30.0
                )
                
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers={k: v for k, v in response.headers.items() if k.lower() not in ["transfer-encoding", "content-encoding"]}
                )
        except Exception as e:
            return Response(
                content=f"<!DOCTYPE html><html><body><h1>Vite Dev Server Not Running</h1><p>Please start Vite: npm run dev:client</p><p>Error: {e}</p></body></html>",
                media_type="text/html"
            )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "5000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
