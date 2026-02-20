import logging
from typing import Dict, Any, Optional

from ..ai_service import ai_service
from prompts import prompt_loader
from ..constants import LANGUAGE_TEST_CONFIG
from ..utils.import_resolver import get_import_guidance
from ..helpers.npm_runner import is_cra_project

logger = logging.getLogger(__name__)


def generate_tests_for_file(
    filepath: str,
    content: str,
    language: str,
    repo_path: str,
    style_guide: str = "",
    existing_test_content: str = "",
    mode: str = "new",
    deps_context: str = "",
    imports_context: str = "",
    tech_stack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])

    import_guidance = get_import_guidance(filepath, language, repo_path, tech_stack)

    is_cra = is_cra_project(repo_path)
    cra_section = ""
    if is_cra:
        cra_section = """
CRA PROJECT NOTES:
- This is a Create React App project using react-scripts
- Tests run via `react-scripts test` (Jest with Babel/JSX support)
- Use @testing-library/react for component testing (render, screen, fireEvent, act, waitFor)
- Mock modules with jest.mock() at top level BEFORE imports
- For React Router components, wrap in <MemoryRouter>
- For context-dependent components, wrap with appropriate providers
- Use act() wrapper for any code that causes state updates
- Test files should be .test.js or .test.jsx
"""

    style_section = ""
    if style_guide:
        style_section = f"""
IMPORTANT - Follow the project's existing test style:
{style_guide}
"""

    deps_section = ""
    if deps_context:
        deps_section = f"""
PROJECT DEPENDENCIES (use these to understand what libraries are available):
{deps_context[:2000]}
"""

    imports_section = ""
    if imports_context:
        imports_section = f"""
RELATED MODULES (imported by this file - understand their interfaces for proper mocking):
{imports_context[:3000]}
"""

    import_section = f"""
IMPORT GUIDELINES FOR THIS PROJECT:
{import_guidance}
{cra_section}"""

    if mode == "augment" and existing_test_content:
        prompt = prompt_loader.get_prompt("unit_test_agent.yml", "generate_unit_tests_augment").format(
            language=language,
            filepath=filepath,
            content=content[:8000],
            existing_test_content=existing_test_content[:6000],
            style_section=style_section,
            deps_section=deps_section,
            imports_section=imports_section,
            import_section=import_section
        )

    else:
        prompt = prompt_loader.get_prompt("unit_test_agent.yml", "generate_unit_tests_new").format(
            language=language,
            framework=config['framework'],
            filepath=filepath,
            content=content[:8000],
            style_section=style_section,
            deps_section=deps_section,
            imports_section=imports_section,
            import_section=import_section
        )

    try:
        test_code = ai_service.call_genai(prompt, temperature=0.1, max_tokens=8192, task_name="unit_test_generation")
        test_code = test_code.strip()
        if test_code.startswith("```"):
            lines = test_code.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            test_code = "\n".join(lines)

        return {"success": True, "test_code": test_code, "source_file": filepath, "mode": mode}
    except Exception as e:
        return {"success": False, "error": str(e), "source_file": filepath, "mode": mode}
