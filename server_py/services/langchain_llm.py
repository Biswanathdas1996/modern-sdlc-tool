"""Custom LangChain LLM wrapper for PwC GenAI."""
from typing import Any, List, Optional, Iterator
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import GenerationChunk

from services.ai_service import AIService
from core.logging import log_info


class PwCGenAILLM(LLM):
    """Custom LangChain LLM wrapper for PwC GenAI."""
    
    temperature: float = 0.7
    max_tokens: int = 4096
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **kwargs):
        """Initialize the PwC GenAI LLM wrapper."""
        super().__init__(**kwargs)
        # Initialize ai_service after parent init
        object.__setattr__(self, 'ai_service', AIService())
    
    @property
    def _llm_type(self) -> str:
        """Return identifier of llm type."""
        return "pwc_genai"
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Call the PwC GenAI API."""
        import asyncio
        
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run async call in sync context
        if loop.is_running():
            # If we're already in an async context, create a task
            import nest_asyncio
            nest_asyncio.apply()
            result = loop.run_until_complete(self._acall_async(prompt, stop, run_manager, **kwargs))
        else:
            result = loop.run_until_complete(self._acall_async(prompt, stop, run_manager, **kwargs))
        
        return result
    
    async def _acall_async(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Async call to PwC GenAI."""
        log_info(f"LLM call with prompt length: {len(prompt)}", "pwc_genai_llm")
        
        ai_service = object.__getattribute__(self, 'ai_service')
        response = await ai_service.call_genai(
            prompt=prompt,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens)
        )
        
        return response
