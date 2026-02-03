"""JIRA integration service."""
import base64
import httpx
from typing import Any, Dict, List, Optional
from core.config import get_settings
from core.logging import log_info, log_error


class JiraService:
    """Service for JIRA API interactions."""
    
    def __init__(self):
        self.settings = get_settings()
        
    def _get_auth_header(self) -> str:
        """Generate Basic Auth header."""
        if not self.settings.jira_email or not self.settings.jira_api_token:
            raise ValueError("JIRA credentials not configured")
            
        auth = base64.b64encode(
            f"{self.settings.jira_email}:{self.settings.jira_api_token}".encode()
        ).decode()
        return f"Basic {auth}"
    
    def _extract_text_from_adf(self, adf: Any) -> str:
        """Extract text from Atlassian Document Format."""
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
    
    async def sync_stories_to_jira(self, user_stories: List[Any], storage) -> Dict[str, Any]:
        """Sync user stories to JIRA."""
        auth_header = self._get_auth_header()
        jira_base_url = (
            f"https://{self.settings.jira_instance_url}/rest/api/3"
        )
        
        results = []
        
        async with httpx.AsyncClient() as client:
            for story in user_stories:
                try:
                    description = self._build_story_description(story)
                    is_subtask = bool(story.parentJiraKey)
                    issue_type_name = "Sub-task" if is_subtask else "Story"
                    
                    issue_data = {
                        "fields": {
                            "project": {"key": self.settings.jira_project_key},
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
                        result_info = {
                            "storyKey": story.storyKey,
                            "jiraKey": data.get("key")
                        }
                        if is_subtask:
                            result_info["parentKey"] = story.parentJiraKey
                            result_info["isSubtask"] = True
                        results.append(result_info)
                    else:
                        log_error(f"JIRA API error for {story.storyKey}: {response.text}", "jira")
                        results.append({
                            "storyKey": story.storyKey,
                            "error": f"Failed: {response.status_code}"
                        })
                except Exception as err:
                    log_error(f"Error syncing story {story.storyKey}", "jira", err)
                    results.append({"storyKey": story.storyKey, "error": str(err)})
        
        success_count = len([r for r in results if r.get("jiraKey")])
        fail_count = len([r for r in results if r.get("error")])
        
        log_info(f"Synced {success_count} stories to JIRA ({fail_count} failed)", "jira")
        
        return {
            "message": f"Synced {success_count} stories to JIRA. "
                      f"{f'{fail_count} failed.' if fail_count > 0 else ''}",
            "results": results
        }
    
    def _build_story_description(self, story: Any) -> Dict[str, Any]:
        """Build JIRA story description in ADF format."""
        description = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": f"As a {story.asA}, I want {story.iWant}, so that {story.soThat}"
                        }
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
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": criteria}]
                                }
                            ]
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
        
        return description
    
    async def get_jira_stories(self) -> List[Dict[str, Any]]:
        """Fetch JIRA stories."""
        auth_header = self._get_auth_header()
        jira_base_url = (
            f"https://{self.settings.jira_instance_url}/rest/api/3"
        )
        
        jql = (
            f"project = {self.settings.jira_project_key} AND "
            "issuetype = Story ORDER BY created DESC"
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{jira_base_url}/search/jql",
                params={
                    "jql": jql,
                    "fields": "summary,description,status,priority,labels,subtasks"
                },
                headers={
                    "Authorization": auth_header,
                    "Accept": "application/json"
                }
            )
            
            if response.status_code != 200:
                log_error(f"JIRA API error: {response.text}", "jira")
                raise Exception(f"Failed to fetch JIRA stories: {response.status_code}")
            
            data = response.json()
            stories = [
                {
                    "key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "description": self._extract_text_from_adf(
                        issue.get("fields", {}).get("description")
                    ),
                    "status": issue.get("fields", {}).get("status", {}).get("name", "Unknown"),
                    "priority": issue.get("fields", {}).get("priority", {}).get("name", "Medium"),
                    "labels": issue.get("fields", {}).get("labels", []),
                    "subtaskCount": len(issue.get("fields", {}).get("subtasks", []))
                }
                for issue in data.get("issues", [])
            ]
            
            log_info(f"Fetched {len(stories)} JIRA stories", "jira")
            return stories
    
    async def get_parent_story_context(self, parent_jira_key: str) -> Optional[str]:
        """Fetch context from parent JIRA story."""
        try:
            auth_header = self._get_auth_header()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{self.settings.jira_instance_url}/rest/api/3/issue/{parent_jira_key}"
                    "?fields=summary,description",
                    headers={
                        "Authorization": auth_header,
                        "Accept": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    issue = response.json()
                    desc_text = self._extract_text_from_adf(
                        issue.get("fields", {}).get("description")
                    )
                    parent_context = (
                        f"Parent Story [{parent_jira_key}]: "
                        f"{issue.get('fields', {}).get('summary', '')}"
                    )
                    if desc_text:
                        parent_context += f"\n\nDescription: {desc_text}"
                    return parent_context
                return None
        except Exception as err:
            log_error(f"Error fetching parent JIRA story", "jira", err)
            return None


# Global JIRA service instance
jira_service = JiraService()
