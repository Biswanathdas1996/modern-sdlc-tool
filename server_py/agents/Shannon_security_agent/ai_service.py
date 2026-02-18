import requests
import os
from pathlib import Path
from dotenv import load_dotenv
from agents.llm_continuation import sync_call_with_continuation

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class AIService:
    def __init__(self):
        self.api_key = os.getenv("PWC_GENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.bearer_token = os.getenv("PWC_GENAI_BEARER_TOKEN")
        self.endpoint_url = os.getenv("PWC_GENAI_ENDPOINT_URL") or os.getenv(
            "GEMINI_API_ENDPOINT",
            "https://genai-sharedservice-americas.pwc.com/completions"
        )

    def call_genai(self, prompt: str, temperature: float = 0.4, max_tokens: int = 8192) -> str:
        if not self.api_key:
            raise ValueError(
                "PwC GenAI API key not configured. Please provide "
                "PWC_GENAI_API_KEY or GEMINI_API_KEY in your .env file."
            )

        request_body = {
            "model": "vertex_ai.gemini-2.0-flash",
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 1,
            "presence_penalty": 0,
            "stream": False,
            "stream_options": None,
            "seed": 25,
            "stop": None,
        }

        headers = {
            "accept": "application/json",
            "API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        return sync_call_with_continuation(
            endpoint_url=self.endpoint_url,
            headers=headers,
            request_body=request_body,
            original_prompt=prompt,
            timeout=180,
        )


ai_service = AIService()
