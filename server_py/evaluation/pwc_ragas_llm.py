"""Custom RAGAS LLM and Embedding wrappers for PwC GenAI API.

Implements InstructorBaseRagasLLM to route all RAGAS metric evaluations
through the PwC GenAI endpoint. Uses structured output parsing by
appending JSON schema instructions to prompts and parsing responses.

Also implements BaseRagasEmbedding for AnswerRelevancy metric.
"""
import json
import asyncio
from typing import Type, TypeVar, Optional, List, Any

from ragas.llms import InstructorBaseRagasLLM
from ragas.embeddings.base import BaseRagasEmbedding

from core.logging import log_debug, log_error

T = TypeVar("T")


class PwcGenAIRagasLLM(InstructorBaseRagasLLM):
    """RAGAS-compatible LLM wrapper for PwC GenAI API.

    Routes all generate/agenerate calls through the existing
    call_pwc_genai_async / call_pwc_genai_sync utilities.
    Handles structured output by appending JSON schema to prompts
    and parsing the response into Pydantic models.
    """

    def __init__(
        self,
        task_name: str = "ragas_evaluation",
        model_override: Optional[str] = None,
    ):
        self.task_name = task_name
        self.model_override = model_override

    def _build_structured_prompt(self, prompt: str, response_model: Type) -> str:
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2)
        return (
            f"{prompt}\n\n"
            f"IMPORTANT: You must respond ONLY with valid JSON that conforms to this schema:\n"
            f"```json\n{schema_str}\n```\n"
            f"Do not include any text outside the JSON object. No markdown, no explanation."
        )

    def _parse_response(self, response_text: str, response_model: Type[T]) -> T:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if text.startswith("```json"):
            text = text[7:].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        try:
            data = json.loads(text)
            return response_model.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            log_error(f"[PwcRagasLLM] Failed to parse response into {response_model.__name__}: {e}", "ragas")
            log_debug(f"[PwcRagasLLM] Raw response: {response_text[:500]}", "ragas")
            raise

    def generate(self, prompt: str, response_model: Type[T]) -> T:
        from utils.pwc_llm import call_pwc_genai_sync

        structured_prompt = self._build_structured_prompt(prompt, response_model)
        log_debug(f"[PwcRagasLLM] sync generate model={response_model.__name__} prompt_len={len(structured_prompt)}", "ragas")

        response_text = call_pwc_genai_sync(
            prompt=structured_prompt,
            temperature=0.01,
            model=self.model_override,
            task_name=self.task_name,
        )
        return self._parse_response(response_text, response_model)

    async def agenerate(self, prompt: str, response_model: Type[T]) -> T:
        from utils.pwc_llm import call_pwc_genai_async

        structured_prompt = self._build_structured_prompt(prompt, response_model)
        log_debug(f"[PwcRagasLLM] async generate model={response_model.__name__} prompt_len={len(structured_prompt)}", "ragas")

        response_text = await call_pwc_genai_async(
            prompt=structured_prompt,
            temperature=0.01,
            model=self.model_override,
            task_name=self.task_name,
        )
        return self._parse_response(response_text, response_model)


class PwcGenAIRagasEmbedding(BaseRagasEmbedding):
    """RAGAS-compatible embedding wrapper using local fastembed model.

    Uses the same BAAI/bge-small-en-v1.5 model as the knowledge base
    for consistent embedding dimensions (384-dim). Required by
    AnswerRelevancy metric for semantic similarity comparison.
    """

    def __init__(self, task_name: str = "ragas_embedding"):
        super().__init__()
        self.task_name = task_name

    def embed_text(self, text: str, **kwargs: Any) -> List[float]:
        from utils.embeddings import generate_embedding

        log_debug(f"[RagasEmbed] sync embed text_len={len(text)}", "ragas")
        result = generate_embedding(text)
        if result is None:
            raise ValueError(f"Embedding generation failed for text of length {len(text)}")
        return result

    async def aembed_text(self, text: str, **kwargs: Any) -> List[float]:
        import asyncio
        from utils.embeddings import generate_embedding

        log_debug(f"[RagasEmbed] async embed text_len={len(text)}", "ragas")
        result = await asyncio.get_event_loop().run_in_executor(None, generate_embedding, text)
        if result is None:
            raise ValueError(f"Embedding generation failed for text of length {len(text)}")
        return result
