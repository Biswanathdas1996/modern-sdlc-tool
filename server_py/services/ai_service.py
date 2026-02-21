"""AI service for GenAI interactions and document generation."""
import os
from functools import partial
from typing import Optional, Callable, Dict, Any, List
from core.config import get_settings
from core.logging import log_info, log_error, log_debug
from core.llm_config import get_llm_config
from utils.text import parse_json_response
from utils.pwc_llm import call_pwc_genai_async, call_pwc_genai_stream, build_pwc_prompt
from prompts import prompt_loader
from services import github_fetcher, generators


class AIService:
    """Service for AI/GenAI operations and document generation."""
    
    def __init__(self):
        self.settings = get_settings()
        self._llm_config = get_llm_config()
        
    async def call_genai(
        self, 
        prompt: str, 
        temperature: Optional[float] = None, 
        max_tokens: Optional[int] = None,
        task_name: Optional[str] = None,
        user_input: Optional[str] = None,
    ) -> str:
        """Call PwC GenAI API using centralized utility.
        
        If task_name is provided, model/temperature/max_tokens are read
        from llm_config.yml (explicit overrides still win).
        
        user_input: raw current user message – passed to guardrails so the
        keyword blocklist only scans the active turn, not conversation history.
        """
        cfg = self._llm_config.get(task_name) if task_name else None
        resolved_temp = temperature if temperature is not None else (cfg.temperature if cfg else 0.2)
        resolved_tokens = max_tokens if max_tokens is not None else (cfg.max_tokens if cfg else 6096)
        model_label = cfg.model if cfg else "defaults"
        log_info(f"Calling PwC GenAI [task={task_name or 'adhoc'}] (prompt length: {len(prompt)} chars)", "ai")
        log_debug(f"AI parameters: model={model_label}, temp={resolved_temp}, max_tokens={resolved_tokens}", "ai")
        
        try:
            response = await call_pwc_genai_async(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                task_name=task_name,
                user_input=user_input,
            )
            log_info("PwC GenAI response received successfully", "ai")
            return response
        except Exception as e:
            error_msg = f"PwC GenAI API Error: {str(e)}"
            log_error(error_msg, "ai")
            raise

    def _task_caller(self, task_name: str):
        """Return a call_genai wrapper pre-bound to a specific task_name."""
        async def _call(prompt: str, temperature: float = None, max_tokens: int = None) -> str:
            return await self.call_genai(prompt, temperature, max_tokens, task_name=task_name)
        return _call
    
    def build_prompt(self, system_message: str, user_message: str) -> str:
        """Build a formatted prompt."""
        return build_pwc_prompt(system_message, user_message)

    def _get_github_headers(self) -> Dict[str, str]:
        """Get GitHub API headers with optional authentication."""
        return github_fetcher.get_github_headers()

    async def fetch_repo_contents(self, repo_url: str) -> str:
        """Fetch repository contents from GitHub."""
        return await github_fetcher.fetch_repo_contents(repo_url)

    async def analyze_repository(self, repo_url: str, project_id: str) -> Dict[str, Any]:
        """Analyze a GitHub repository and extract key information."""
        repo_context = await self.fetch_repo_contents(repo_url)

        system_prompt = prompt_loader.get_prompt("ai_service.yml", "analyze_repository_system")
        user_prompt = prompt_loader.get_prompt("ai_service.yml", "analyze_repository_user").format(
            repo_context=repo_context
        )
        
        prompt = self.build_prompt(system_prompt, user_prompt)
        response_text = await self.call_genai(prompt, task_name="repo_analysis")
        
        analysis_data = parse_json_response(response_text)
        
        return {
            **analysis_data,
            "projectId": project_id,
        }

    async def generate_documentation(self, analysis: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
        """Generate technical documentation for a project."""
        return await generators.generate_documentation(
            self._task_caller("documentation_generation"), self.build_prompt, analysis, project, self.fetch_repo_contents
        )

    async def generate_bpmn_diagram(self, documentation: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate BPMN diagrams from documentation."""
        return await generators.generate_bpmn_diagram(
            self._task_caller("bpmn_diagram"), self.build_prompt, documentation, analysis
        )

    async def transcribe_audio(self, audio_buffer: bytes) -> str:
        """Transcribe audio to text using PwC GenAI whisper model."""
        from utils.pwc_llm import call_pwc_transcribe_async
        return await call_pwc_transcribe_async(audio_buffer, task_name="audio_transcription")

    def _task_streamer(self, task_name: str):
        """Return a stream_genai wrapper pre-bound to a specific task_name."""
        def _stream(prompt: str, **kwargs):
            kwargs.pop("task_name", None)
            return call_pwc_genai_stream(prompt=prompt, task_name=task_name, **kwargs)
        return _stream

    async def generate_brd(
        self,
        feature_request: Dict[str, Any],
        analysis: Optional[Dict[str, Any]],
        documentation: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """Generate Business Requirements Document with comprehensive context."""
        return await generators.generate_brd(
            self._task_caller("brd_generation"), self.build_prompt,
            feature_request, analysis, documentation, database_schema,
            knowledge_context, on_chunk
        )

    async def generate_brd_streaming(
        self,
        feature_request: Dict[str, Any],
        analysis: Optional[Dict[str, Any]],
        documentation: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
        on_chunk: Optional[Callable[[str], None]] = None,
    ):
        """Generate BRD with true streaming — async generator yielding chunks."""
        async for item in generators.generate_brd_streaming(
            self._task_streamer("brd_generation"), self.build_prompt,
            feature_request, analysis, documentation, database_schema,
            knowledge_context, on_chunk,
        ):
            yield item

    def _task_caller_factory(self):
        """Return a factory that creates task-specific call_genai wrappers."""
        def factory(task_name: str):
            return self._task_caller(task_name)
        return factory

    async def generate_brd_parallel(
        self,
        feature_request: Dict[str, Any],
        analysis: Optional[Dict[str, Any]],
        documentation: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
    ):
        """Generate BRD with parallel section calls — async generator yielding section events."""
        async for item in generators.generate_brd_parallel(
            self._task_caller_factory(), self.build_prompt,
            feature_request, analysis, documentation, database_schema,
            knowledge_context,
        ):
            yield item

    async def generate_test_cases(self, brd: Dict[str, Any], analysis: Optional[Dict[str, Any]], documentation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate test cases from BRD."""
        return await generators.generate_test_cases(
            self._task_caller("test_case_generation"), self.build_prompt, brd, analysis, documentation
        )

    async def generate_test_data(self, test_cases: List[Dict[str, Any]], brd: Dict[str, Any], documentation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate test data for test cases."""
        return await generators.generate_test_data(
            self._task_caller("test_data_generation"), self.build_prompt, test_cases, brd, documentation
        )

    async def generate_user_stories(
        self,
        brd: Dict[str, Any],
        documentation: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        parent_context: Optional[str],
        knowledge_context: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Generate user stories from BRD."""
        return await generators.generate_user_stories(
            self._task_caller("user_story_generation"), self.build_prompt,
            brd, documentation, database_schema, parent_context, knowledge_context
        )

    async def generate_copilot_prompt(
        self,
        user_stories: List[Dict[str, Any]],
        documentation: Optional[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]],
        database_schema: Optional[Dict[str, Any]],
        feature_request: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a detailed GitHub Copilot prompt."""
        return await generators.generate_copilot_prompt(
            self._task_caller("copilot_prompt"), self.build_prompt,
            user_stories, documentation, analysis, database_schema, feature_request
        )

    async def find_related_stories(self, feature_description: str, jira_stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find related JIRA stories based on feature description."""
        return await generators.find_related_stories(
            self._task_caller("related_stories"), self.build_prompt, feature_description, jira_stories
        )


# Global AI service instance
ai_service = AIService()
