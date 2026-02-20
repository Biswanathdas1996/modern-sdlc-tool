import logging
from typing import Dict, Any

from ..ai_service import ai_service
from prompts import prompt_loader
from ..constants import MAX_FIX_ATTEMPTS
from ..utils.error_classifier import classify_test_error, get_error_specific_guidance
from ..helpers.mocking_guide import get_mocking_guidance
from ..helpers.npm_runner import is_cra_project

logger = logging.getLogger(__name__)


def fix_failing_tests(
    filepath: str,
    source_content: str,
    test_code: str,
    error_output: str,
    language: str,
    attempt: int,
    deps_context: str = "",
    repo_path: str = "",
) -> Dict[str, Any]:
    logger.info(f"Attempting to fix failing tests for {filepath} (attempt {attempt}/{MAX_FIX_ATTEMPTS})")

    error_classification = classify_test_error(error_output, language)
    error_type = error_classification["type"]
    logger.info(f"Error classified as: {error_type} ({error_classification['priority']} priority)")

    is_cra = is_cra_project(repo_path) if repo_path else False
    cra_note = ""
    if is_cra:
        cra_note = """
IMPORTANT: This is a Create React App (CRA) project using react-scripts.
- Tests are run with `react-scripts test` which uses Jest under the hood with Babel transforms
- React components should be tested with @testing-library/react (render, screen, fireEvent, act)
- Mock modules with jest.mock() at the top level
- For components using React Router, wrap in MemoryRouter
- For components using context providers, wrap appropriately
- Use act() for state updates and async operations
"""

    prompt = prompt_loader.get_prompt("unit_test_agent.yml", "fix_failing_tests").format(
        language=language,
        attempt=attempt,
        max_attempts=MAX_FIX_ATTEMPTS,
        filepath=filepath,
        source_content=source_content[:6000],
        test_code=test_code[:6000],
        error_output=error_output[:3000],
        deps_context_section=f"PROJECT DEPENDENCIES:{deps_context[:1500]}" if deps_context else "",
        cra_note=cra_note,
        mocking_guidance=get_mocking_guidance(language),
        error_type=error_type,
        error_specific_guidance=get_error_specific_guidance(error_type, filepath, language, repo_path),
        fix_strategy_note="- Be aggressive: If a test is too complex to fix reliably, REMOVE it" if attempt >= 2 else "- Fix each error systematically",
        focus_note="- Focus ONLY on tests that will definitely pass" if attempt >= 2 else "- Attempt to fix all tests",
        better_less_note="- It's better to have 3 passing tests than 10 failing tests" if attempt >= 3 else ""
    )

    try:
        logger.info("Calling AI service to fix failing tests...")
        fixed_code = ai_service.call_genai(prompt, temperature=0.15, max_tokens=8192)
        fixed_code = fixed_code.strip()
        if fixed_code.startswith("```"):
            lines = fixed_code.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            fixed_code = "\n".join(lines)
        logger.info(f"Successfully generated fixed test code ({len(fixed_code)} chars)")
        return {"success": True, "test_code": fixed_code}
    except Exception as e:
        logger.error(f"Failed to fix tests: {e}")
        return {"success": False, "error": str(e)}


def extract_passing_tests_only(
    filepath: str,
    source_content: str,
    test_code: str,
    error_output: str,
    language: str,
) -> Dict[str, Any]:
    prompt = prompt_loader.get_prompt("unit_test_agent.yml", "remove_failing_tests").format(
        language=language,
        filepath=filepath,
        source_content=source_content[:4000],
        test_code=test_code[:6000],
        error_output=error_output[:3000]
    )

    try:
        cleaned_code = ai_service.call_genai(prompt, temperature=0.1, max_tokens=8192)
        cleaned_code = cleaned_code.strip()
        if cleaned_code.startswith("```"):
            lines = cleaned_code.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_code = "\n".join(lines)
        return {"success": True, "test_code": cleaned_code}
    except Exception as e:
        return {"success": False, "error": str(e)}
