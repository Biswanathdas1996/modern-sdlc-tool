import os
import base64
from typing import Any, Dict, List, Optional
import httpx
from ai import find_related_stories


def extract_text_from_adf(adf: Any) -> str:
    """Extract text content from Atlassian Document Format (ADF)."""
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


def get_jira_credentials() -> Dict[str, str]:
    """Get JIRA credentials from environment variables."""
    return {
        "email": os.environ.get("JIRA_EMAIL"),
        "token": os.environ.get("JIRA_API_TOKEN"),
        "instance_url": os.environ.get("JIRA_INSTANCE_URL", "daspapun21.atlassian.net"),
        "project_key": os.environ.get("JIRA_PROJECT_KEY", "KAN")
    }


def get_jira_auth_header(email: str, token: str) -> str:
    """Generate Basic Auth header for JIRA API."""
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    return f"Basic {auth}"


async def sync_stories_to_jira(user_stories: List[Any], storage) -> Dict[str, Any]:
    """Sync user stories to JIRA as issues."""
    creds = get_jira_credentials()
    
    if not creds["email"] or not creds["token"]:
        raise ValueError("JIRA credentials not configured. Please add JIRA_EMAIL and JIRA_API_TOKEN secrets.")
    
    auth_header = get_jira_auth_header(creds["email"], creds["token"])
    jira_base_url = f"https://{creds['instance_url']}/rest/api/3"
    
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
                        "project": {"key": creds["project_key"]},
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
                        "Authorization": auth_header,
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


async def get_jira_stories() -> List[Dict[str, Any]]:
    """Fetch JIRA stories from the configured project."""
    creds = get_jira_credentials()
    
    if not creds["email"] or not creds["token"]:
        raise ValueError("JIRA credentials not configured.")
    
    auth_header = get_jira_auth_header(creds["email"], creds["token"])
    jira_base_url = f"https://{creds['instance_url']}/rest/api/3"
    
    jql = f"project = {creds['project_key']} AND issuetype = Story ORDER BY created DESC"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{jira_base_url}/search/jql",
            params={"jql": jql, "fields": "summary,description,status,priority,labels,subtasks"},
            headers={"Authorization": auth_header, "Accept": "application/json"}
        )
        
        if response.status_code != 200:
            print(f"JIRA API error: {response.text}")
            raise Exception(f"Failed to fetch JIRA stories: {response.status_code}")
        
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


async def find_related_jira_stories(feature_description: str) -> List[Dict[str, Any]]:
    """Find JIRA stories related to the given feature description."""
    creds = get_jira_credentials()
    
    if not creds["email"] or not creds["token"]:
        return []
    
    auth_header = get_jira_auth_header(creds["email"], creds["token"])
    jira_base_url = f"https://{creds['instance_url']}/rest/api/3"
    
    jql = f"project = {creds['project_key']} ORDER BY created DESC"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{jira_base_url}/search/jql",
            params={"jql": jql, "fields": "summary,description,status,priority,labels,issuetype", "maxResults": 100},
            headers={"Authorization": auth_header, "Accept": "application/json"}
        )
        
        if response.status_code != 200:
            return []
        
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
            return []
        
        related_stories = await find_related_stories(feature_description, jira_stories)
        return related_stories


async def sync_subtask_to_jira(story: Any, parent_key: str, storage) -> Dict[str, Any]:
    """Sync a single user story as a subtask to a JIRA parent story."""
    creds = get_jira_credentials()
    
    if not creds["email"] or not creds["token"]:
        raise ValueError("JIRA credentials not configured.")
    
    auth_header = get_jira_auth_header(creds["email"], creds["token"])
    jira_base_url = f"https://{creds['instance_url']}/rest/api/3"
    
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
            "project": {"key": creds["project_key"]},
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
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json=issue_data
        )
        
        if response.status_code == 201:
            data = response.json()
            storage.update_user_story(story.id, {"parentJiraKey": parent_key, "jiraKey": data.get("key")})
            return {
                "storyKey": story.storyKey,
                "jiraKey": data.get("key"),
                "parentKey": parent_key,
                "message": f"Created subtask {data.get('key')} under {parent_key}"
            }
        else:
            print(f"JIRA API error: {response.text}")
            raise Exception(f"Failed to create subtask: {response.status_code}")


async def get_jira_parent_story_context(parent_jira_key: str) -> Optional[str]:
    """Fetch context from a parent JIRA story."""
    creds = get_jira_credentials()
    
    if not creds["email"] or not creds["token"]:
        return None
    
    try:
        auth_header = get_jira_auth_header(creds["email"], creds["token"])
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{creds['instance_url']}/rest/api/3/issue/{parent_jira_key}?fields=summary,description",
                headers={"Authorization": auth_header, "Accept": "application/json"}
            )
            
            if response.status_code == 200:
                issue = response.json()
                desc_text = extract_text_from_adf(issue.get("fields", {}).get("description"))
                parent_context = f"Parent Story [{parent_jira_key}]: {issue.get('fields', {}).get('summary', '')}"
                if desc_text:
                    parent_context += f"\n\nDescription: {desc_text}"
                return parent_context
            return None
    except Exception as err:
        print(f"Error fetching parent JIRA story: {err}")
        return None
