"""NVIDIA NeMo Guardrails – central input/output screening service.

All LLM queries pass through this module via ``check_input_async`` /
``check_input_sync`` *before* being forwarded to the PwC GenAI endpoint.
The service is initialised lazily (first use) and is thread / async-safe.

Architecture
------------
* NeMo Guardrails is configured from ``server_py/guardrails/config.yml``.
* Colang files in ``server_py/guardrails/rails/`` define pattern-based
  input rails (jailbreak, prompt-injection, harmful content …).
* ``prompts.yml`` provides LLM-as-judge templates for the ``self check
  input`` and ``self check output`` built-in rails.
* The PwC GenAI LLM (``PwCGenAILLM``) is registered as the main LLM so
  that the LLM-based self-check calls use the same endpoint.
* A ``passthrough.co`` Colang file returns ``GUARDRAILS_INPUT_APPROVED``
  when no input rail fires – this prevents NeMo from trying to call the
  main LLM for *response generation* (that job belongs to ``pwc_llm.py``).

Graceful degradation
--------------------
If ``nemoguardrails`` is not installed the module logs a warning and all
guardrail checks become no-ops so the application still starts.  Install
the package with ``pip install nemoguardrails`` to enable full protection.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from core.logging import log_info, log_warning, log_error, log_debug

logger = logging.getLogger(__name__)

# Sentinel returned by the pass-through Colang flow when no rail fires.
_PASS_SENTINEL = "GUARDRAILS_INPUT_APPROVED"

# Known refusal prefixes emitted by the Colang ``define bot refuse …``
# declarations.  Any response that starts with one of these is treated as
# a blocked request.
_REFUSAL_PREFIXES = (
    "I'm unable to process that request",
    "I'm unable to assist with that request",
    "I'm unable to reveal credential",
    "I'm an AI assistant and I cannot",
    "I cannot",
    "I'm not able to",
    "I am unable to",
)

# ---------------------------------------------------------------------------
# Fast-path keyword blocklist
# ---------------------------------------------------------------------------
# These patterns are matched against the *raw prompt text* (case-insensitive)
# BEFORE NeMo even runs.  This guarantees catch even when the harmful phrase
# is buried inside a large assembled system+user prompt, or when NeMo is not
# available / has not been installed yet.
#
# Format: (regex_pattern, human_readable_rail_name)
# ---------------------------------------------------------------------------
import re as _re

_KEYWORD_BLOCKLIST: list[tuple[str, str]] = [
    # Weapons / explosives / bombs
    (r"\bmake\s+a?\s*bomb\b",            "check_weapons"),
    (r"\bbuild\s+a?\s*bomb\b",           "check_weapons"),
    (r"\bhow\s+to\s+.{0,30}bomb\b",      "check_weapons"),
    (r"\b(explosive|explosives)\b.*\b(make|build|create|instruct|synthesize)\b", "check_weapons"),
    (r"\b(make|build|create|instruct|synthesize)\b.*\b(explosive|explosives)\b", "check_weapons"),
    (r"\bhomemade\s+(weapon|bomb|grenade|ied|napalm|thermite)\b", "check_weapons"),
    (r"\b(pipe\s+bomb|ied|improvised\s+explosive|molotov)\b",    "check_weapons"),
    (r"\b(chemical\s+weapon|nerve\s+agent|biological\s+weapon)\b", "check_weapons"),
    (r"\b3d\s*print\s+(a\s+)?gun\b",      "check_weapons"),
    (r"\bhow\s+to\s+.{0,30}(manufacture|obtain)\s+.{0,20}(weapon|firearm|gun)\b", "check_weapons"),
    # Violence / harm to people
    (r"\bhow\s+to\s+kill\s+(a\s+)?(person|someone|people|human)\b", "check_violence"),
    (r"\bwant\s+to\s+(kill|hurt|harm|poison|murder)\s+(someone|a\s+person|people)\b", "check_violence"),
    (r"\bhow\s+to\s+(hurt|harm|poison)\s+(someone|a\s+person)\b", "check_violence"),
    (r"\bhow\s+to\s+stalk\s+(someone|a\s+person)\b",             "check_violence"),
    # Illegal drugs
    (r"\b(synthesize|cook|make|produce)\s+.{0,30}(meth(amphetamine)?|fentanyl|heroin|cocaine)\b", "check_drugs"),
    # Malware / cyberattacks
    (r"\b(write|create|build|generate)\s+.{0,20}(malware|ransomware|keylogger|trojan|rootkit)\b", "check_cyberattack"),
    (r"\bddos\s+attack\b",               "check_cyberattack"),
    (r"\blaunch\s+a\s+(ddos|cyber)\s+attack\b", "check_cyberattack"),
]

# Pre-compile the patterns for performance
_COMPILED_BLOCKLIST: list[tuple[_re.Pattern, str]] = [
    (_re.compile(pattern, _re.IGNORECASE | _re.DOTALL), rail)
    for pattern, rail in _KEYWORD_BLOCKLIST
]

_BLOCKED_RESPONSE = (
    "I'm unable to assist with that request. It violates the acceptable use policy."
)

_GUARDRAILS_DIR = Path(__file__).parent.parent / "guardrails"


class GuardrailsViolationError(Exception):
    """Raised when NeMo Guardrails blocks an LLM input or output.

    Attributes
    ----------
    message:
        Human-readable explanation / bot-refusal message.
    rail_name:
        Name of the rail that triggered the block (if determinable).
    """

    def __init__(self, message: str, rail_name: str = "unknown") -> None:
        self.message = message
        self.rail_name = rail_name
        super().__init__(f"[GuardrailsViolation:{rail_name}] {message}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_refusal(response: str) -> bool:
    """Return True if *response* is a guardrails refusal message."""
    if not response or response.strip() == _PASS_SENTINEL:
        return False
    text = response.strip()
    return any(text.startswith(prefix) for prefix in _REFUSAL_PREFIXES)


def _detect_rail(response: str) -> str:
    """Best-effort detection of which rail produced *response*."""
    lower = response.lower()
    if "jailbreak" in lower or "instruction" in lower or "override" in lower:
        return "check_jailbreak"
    if "injection" in lower:
        return "check_prompt_injection"
    if "harmful" in lower or "acceptable use" in lower:
        return "check_harmful_request"
    if "credential" in lower or "key" in lower or "password" in lower:
        return "check_credential_exposure"
    if "human" in lower or "impersona" in lower:
        return "check_impersonation"
    return "self_check_input"


# ---------------------------------------------------------------------------
# GuardrailsService
# ---------------------------------------------------------------------------

class GuardrailsService:
    """Initialises NeMo Guardrails and exposes input-check methods.

    Instantiate via the module-level ``get_guardrails_service()`` factory
    which caches the singleton.
    """

    def __init__(self) -> None:
        self._rails = None          # nemoguardrails.LLMRails | None
        self._available = False     # True when nemoguardrails is installed
        self._enabled = True        # Can be toggled via environment variable

        self._init()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init(self) -> None:
        import os
        if os.getenv("NEMO_GUARDRAILS_DISABLED", "").lower() in ("1", "true", "yes"):
            log_warning(
                "NeMo Guardrails disabled via NEMO_GUARDRAILS_DISABLED env var",
                "guardrails",
            )
            self._enabled = False
            return

        try:
            from nemoguardrails import RailsConfig, LLMRails  # type: ignore
        except ImportError:
            log_warning(
                "nemoguardrails package not installed – guardrails checks are disabled. "
                "Run `pip install nemoguardrails` to enable protection.",
                "guardrails",
            )
            self._available = False
            return

        try:
            config = RailsConfig.from_path(str(_GUARDRAILS_DIR))
            llm = self._build_llm()
            self._rails = LLMRails(config, llm=llm)
            self._available = True
            log_info(
                f"NeMo Guardrails initialised from {_GUARDRAILS_DIR}",
                "guardrails",
            )
        except Exception as exc:
            log_error(
                f"Failed to initialise NeMo Guardrails: {exc} – "
                "continuing without guardrails protection.",
                "guardrails",
            )
            self._available = False

    def _build_llm(self):
        """Return the PwCGenAILLM instance used for LLM-based self-check rails."""
        try:
            from services.langchain_llm import PwCGenAILLM  # type: ignore
            from core.llm_config import get_llm_config

            cfg = get_llm_config().get("defaults")
            return PwCGenAILLM(
                temperature=0.1,         # low temp for policy evaluation
                max_tokens=16,           # we only need "yes" / "no"
                task_name="guardrails_check",
            )
        except Exception as exc:
            log_warning(
                f"Could not create PwCGenAILLM for guardrails: {exc}",
                "guardrails",
            )
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _keyword_check(
        self,
        prompt: str,
        task_name: Optional[str],
        user_input: Optional[str] = None,
    ) -> None:
        """Fast-path blocklist check (regex-based, no LLM needed).

        Scans *user_input* when provided (current user turn only), otherwise
        scans the full *prompt*.  Using *user_input* prevents false positives
        where a previous harmful message appears in conversation history that
        is embedded in the assembled prompt but should not block a new,
        legitimate request.
        """
        target = user_input if user_input is not None else prompt
        for compiled, rail in _COMPILED_BLOCKLIST:
            if compiled.search(target):
                log_warning(
                    f"Keyword blocklist BLOCKED [rail={rail}] "
                    f"(task={task_name or 'adhoc'}, matched={compiled.pattern!r})",
                    "guardrails",
                )
                raise GuardrailsViolationError(
                    message=_BLOCKED_RESPONSE,
                    rail_name=rail,
                )

    async def check_input_async(
        self,
        prompt: str,
        task_name: Optional[str] = None,
        user_input: Optional[str] = None,
    ) -> None:
        """Validate the prompt against all configured input rails.

        Parameters
        ----------
        prompt:
            The full assembled prompt (system + history + current query).
        task_name:
            Optional task identifier (used for logging only).
        user_input:
            The raw current user message.  When supplied, the fast-path
            keyword blocklist runs only on *this* text so that harmful
            phrases in conversation history do not block new legitimate
            requests.

        Raises
        ------
        GuardrailsViolationError
            If any input rail blocks the prompt.
        """
        if not self._enabled or not self._available or self._rails is None:
            # Even when NeMo is not loaded/available, always run keyword check
            self._keyword_check(prompt, task_name, user_input)
            return

        log_debug(
            f"Guardrails input check → task={task_name or 'adhoc'} "
            f"prompt_len={len(prompt)}",
            "guardrails",
        )

        # 1. Fast-path keyword blocklist (current user input only)
        self._keyword_check(prompt, task_name, user_input)

        # 2. NeMo Colang pattern rails + LLM-based self-check
        try:
            response: str = await self._rails.generate_async(
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception as exc:
            # Never let a guardrails error silently swallow a legitimate request.
            # Log and allow through so the application stays operational.
            log_error(
                f"NeMo Guardrails generate_async error (task={task_name}): {exc} – "
                "allowing request through.",
                "guardrails",
            )
            return

        log_debug(f"Guardrails response: {response!r}", "guardrails")

        if _is_refusal(response):
            rail = _detect_rail(response)
            log_warning(
                f"Guardrails BLOCKED prompt [rail={rail}] "
                f"(task={task_name or 'adhoc'}, prompt_len={len(prompt)})",
                "guardrails",
            )
            raise GuardrailsViolationError(message=response.strip(), rail_name=rail)

        log_debug("Guardrails: prompt approved.", "guardrails")

    def check_input_sync(
        self,
        prompt: str,
        task_name: Optional[str] = None,
        user_input: Optional[str] = None,
    ) -> None:
        """Synchronous variant of :meth:`check_input_async`.

        Runs the async check inside a new event-loop when called from a
        synchronous context (e.g. ``call_pwc_genai_sync``).

        Raises
        ------
        GuardrailsViolationError
            If any input rail blocks the prompt.
        """
        if not self._enabled or not self._available or self._rails is None:
            # Even when NeMo is not available, always run keyword check
            self._keyword_check(prompt, task_name, user_input)
            return

        # 1. Fast-path keyword blocklist (current user input only)
        self._keyword_check(prompt, task_name, user_input)

        # 2. NeMo Colang rails + LLM self-check
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # We are already inside an async loop (e.g. nest_asyncio context).
            import nest_asyncio  # type: ignore
            nest_asyncio.apply()
            loop.run_until_complete(self.check_input_async(prompt, task_name, user_input))
        else:
            loop.run_until_complete(self.check_input_async(prompt, task_name, user_input))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True when nemoguardrails is installed and rails loaded."""
        return self._available

    @property
    def is_enabled(self) -> bool:
        """True when guardrails are active (not disabled via env var)."""
        return self._enabled


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_guardrails_service() -> GuardrailsService:
    """Return the module-level singleton :class:`GuardrailsService`."""
    return GuardrailsService()


# Convenience top-level functions -------------------------------------------

async def check_input_async(
    prompt: str,
    task_name: Optional[str] = None,
    user_input: Optional[str] = None,
) -> None:
    """Module-level shortcut for :meth:`GuardrailsService.check_input_async`."""
    await get_guardrails_service().check_input_async(prompt, task_name, user_input)


def check_input_sync(
    prompt: str,
    task_name: Optional[str] = None,
    user_input: Optional[str] = None,
) -> None:
    """Module-level shortcut for :meth:`GuardrailsService.check_input_sync`."""
    get_guardrails_service().check_input_sync(prompt, task_name, user_input)
