import os
import re
from pathlib import Path
from typing import Dict, Any

from .ai_service import ai_service
from prompts import prompt_loader
from .constants import logger, LANGUAGE_TEST_CONFIG, MAX_FIX_ATTEMPTS
from .test_runner import is_cra_project


def classify_test_error(error_output: str, language: str) -> Dict[str, str]:
    """Classify test error type for targeted fixing."""
    error_output_lower = error_output.lower()
    
    if re.search(r"cannot find module|modulenotfounderror|importerror|no module named|cannot resolve", error_output_lower):
        return {
            "type": "IMPORT_ERROR",
            "priority": "critical",
            "description": "Module import path is incorrect"
        }
    
    if re.search(r"is not a function|mockreturnvalue.*undefined|mock.*not defined|cannot read.*undefined", error_output_lower):
        return {
            "type": "MOCK_ERROR",
            "priority": "high",
            "description": "Mock not properly configured or defined after imports"
        }
    
    if re.search(r"is not a function|undefined.*function|attributeerror|has no attribute|is undefined", error_output_lower):
        return {
            "type": "ATTRIBUTE_ERROR",
            "priority": "high",
            "description": "Testing function/method that doesn't exist in source"
        }
    
    if re.search(r"promise|async|await|then.*catch|unhandledpromise", error_output_lower):
        return {
            "type": "ASYNC_ERROR",
            "priority": "medium",
            "description": "Async function not properly handled"
        }
    
    if re.search(r"syntaxerror|unexpected token|invalid syntax", error_output_lower):
        return {
            "type": "SYNTAX_ERROR",
            "priority": "critical",
            "description": "Code has syntax errors"
        }
    
    if re.search(r"expected.*received|assertionerror|expected.*to.*but|test failed", error_output_lower):
        return {
            "type": "ASSERTION_ERROR",
            "priority": "low",
            "description": "Test assertion logic is incorrect"
        }
    
    return {
        "type": "UNKNOWN",
        "priority": "medium",
        "description": "Unknown error type"
    }


def calculate_correct_import_path(test_file_path: str, source_file_path: str, tech_stack: Dict[str, Any] = None) -> str:
    """Calculate the correct import path from test file to source file."""
    test_path = Path(test_file_path)
    source_path = Path(source_file_path)
    
    if tech_stack:
        import_style = tech_stack.get("import_style", "relative")
        path_alias = tech_stack.get("path_alias")
        has_src_dir = tech_stack.get("has_src_dir", False)
        
        if path_alias and import_style == "alias":
            source_str = str(source_path)
            if source_str.startswith("src/") or source_str.startswith("src\\"):
                source_str = source_str[4:]
            source_no_ext = str(Path(source_str).with_suffix(""))
            return f"{path_alias}/{source_no_ext.replace(chr(92), '/')}"
    
    try:
        test_dir = test_path.parent
        rel_path = Path(os.path.relpath(source_path, test_dir))
        
        rel_path_no_ext = rel_path.with_suffix("")
        import_path = str(rel_path_no_ext).replace(chr(92), "/")
        
        if not import_path.startswith("..") and not import_path.startswith("/"):
            import_path = "./" + import_path
        
        return import_path
    except Exception as e:
        logger.warning(f"Error calculating import path: {e}")
        return f"./{source_path.stem}"


def get_mocking_guidance(language: str) -> str:
    if language == "python":
        return "4. Use unittest.mock.patch, unittest.mock.MagicMock, or pytest-mock (mocker fixture) for mocking"
    elif language in ("javascript", "typescript"):
        return "4. Use jest.mock() for module mocking, jest.fn() for function mocking, and jest.spyOn() for method spying"
    elif language == "go":
        return "4. Use interfaces and dependency injection for mocking; create mock structs that implement the required interfaces"
    elif language == "java":
        return "4. Use Mockito (@Mock, @InjectMocks, when().thenReturn()) for mocking dependencies"
    else:
        return "4. Use the standard mocking library for this language to mock all external dependencies"


def get_error_specific_guidance(error_type: str, filepath: str, language: str, repo_path: str = "") -> str:
    """Provide targeted guidance based on error type."""
    
    if error_type == "IMPORT_ERROR":
        return """**CRITICAL FIX NEEDED: Import path is wrong!**

ACTION REQUIRED:
1. Check the error message to see which import is failing
2. The test file needs to import from the source file
3. Use RELATIVE imports (e.g., '../api/APIService' or './APIService')
4. Remove file extensions in imports (use 'APIService' not 'APIService.js')
5. Count the directory levels carefully - each '../' goes up one level

EXAMPLE:
If test is at:    __tests__/api/APIService.test.js
And source is at: api/APIService.js
Then import:      import { APIService } from '../../api/APIService';

DO NOT use absolute imports like '/api/APIService' - they will fail!
"""
    
    elif error_type == "MOCK_ERROR":
        return """**CRITICAL FIX NEEDED: Mock configuration is broken!**

ACTION REQUIRED:
1. Move ALL jest.mock() calls to the VERY TOP of the file (line 1-5)
2. Mocks MUST be defined BEFORE any imports
3. Mock the MODULE PATH, not the imported variable

CORRECT ORDER:
```javascript
// 1. Mocks FIRST (top of file)
jest.mock('axios');
jest.mock('../services/api');

// 2. Then imports
import React from 'react';
import { APIService } from '../api/APIService';

// 3. Then tests
describe('APIService', () => {...});
```
"""
    
    elif error_type == "ATTRIBUTE_ERROR":
        return """**CRITICAL FIX NEEDED: Testing functions that don't exist!**

ACTION REQUIRED:
1. Read the SOURCE FILE above carefully
2. Only test functions/methods that ACTUALLY EXIST in the source
3. Check exact function names (case-sensitive)
4. Remove tests for functions you assumed exist but don't
"""
    
    elif error_type == "ASYNC_ERROR":
        return """**FIX NEEDED: Async/Promise handling is incorrect!**

ACTION REQUIRED:
1. If testing async function, mark test as async: it('test', async () => {
2. Use await before calling async functions
3. For React Testing Library: use waitFor() or findBy*() queries
4. Mock promises to resolve/reject properly
"""
    
    elif error_type == "SYNTAX_ERROR":
        return """**CRITICAL FIX: Syntax error in generated code!**

ACTION REQUIRED:
1. Check for missing brackets, parentheses, braces
2. Check for incorrect JSX syntax
3. Check for incorrect string quotes
4. Ensure proper async/await syntax
"""
    
    elif error_type == "ASSERTION_ERROR":
        return """**FIX NEEDED: Assertion values don't match actual behavior!**

ACTION REQUIRED:
1. Re-read the SOURCE CODE to understand what it actually does
2. Update expected values to match real behavior
3. If uncertain, use simpler assertions (e.g., toBeDefined() instead of exact values)
"""
    
    else:
        return """**General debugging needed - carefully review the error message and fix accordingly.**"""


def get_import_guidance(filepath: str, language: str, repo_path: str, tech_stack: Dict[str, Any] = None) -> str:
    """Generate import path guidance based on tech stack and project structure."""
    if language == "python":
        return """Python imports:
- Use absolute imports from the project root (e.g., 'from module_name import function')
- If the project has a package structure, use fully qualified imports
- Mock external dependencies with `unittest.mock.patch` or `pytest-mock`
Example: `from my_module.utils import helper_function`"""

    elif language in ("javascript", "typescript"):
        if not tech_stack:
            return """JavaScript/TypeScript imports:
- Use relative imports for nearby files (e.g., '../utils/helper')
- Use absolute imports for node_modules packages
Example: `import { helperFunction } from '../utils/helper';`"""
        
        import_style = tech_stack.get("import_style", "relative")
        path_alias = tech_stack.get("path_alias")
        has_src_dir = tech_stack.get("has_src_dir", False)
        is_react = tech_stack.get("is_react", False)
        test_location = tech_stack.get("test_location", "separate-dir")
        
        source_path = Path(filepath)
        guidance = f"""JavaScript/TypeScript imports for this project:
"""
        
        if path_alias and import_style == "alias":
            guidance += f"- This project uses '{path_alias}/' path alias for absolute imports\n"
            if has_src_dir:
                guidance += f"- Example: `import {{ Component }} from '{path_alias}/components/MyComponent';`\n"
            else:
                guidance += f"- Example: `import {{ helper }} from '{path_alias}/utils/helper';`\n"
        elif import_style == "absolute" and has_src_dir:
            guidance += "- Use absolute imports from src directory\n"
            guidance += "- Example: `import { Component } from 'src/components/MyComponent';`\n"
        else:
            guidance += "- Use relative imports based on file location\n"
            if test_location == "next-to-source":
                guidance += "- Test files are next to source files, so imports are simple (e.g., './MyComponent')\n"
                guidance += f"- Example: `import {{ Component }} from './{source_path.stem}';`\n"
            elif test_location == "mirror-structure":
                guidance += "- Tests mirror source structure in __tests__/\n"
                if str(source_path).startswith("src/"):
                    rel_path = "../" + str(source_path)
                    guidance += f"- Example: `import {{ Component }} from '{rel_path}';`\n"
                else:
                    guidance += f"- Example: `import {{ helper }} from '../{filepath}';`\n"
            else:
                if has_src_dir and str(source_path).startswith("src/"):
                    guidance += "- Tests are in __tests__/ directory, source is in src/\n"
                    guidance += f"- Example: `import {{ Component }} from '../{filepath}';`\n"
                else:
                    guidance += f"- Example: `import {{ helper }} from '../{filepath}';`\n"
        
        if is_react:
            guidance += """
React-specific:
- Import React: `import React from 'react';` (or destructure hooks)
- Import testing utilities: `import { render, screen, fireEvent } from '@testing-library/react';`
- Mock components with jest.mock()"""
        
        return guidance.strip()
    
    else:
        return f"{language} imports: Use standard import conventions for this language"


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
    config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])

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
    tech_stack: Dict[str, Any] = None,
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
        test_code = ai_service.call_genai(prompt, temperature=0.1, max_tokens=8192)
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


def determine_test_path(source_file: str, language: str, repo_path: str, tech_stack: Dict[str, Any] = None) -> str:
    """Determine test file path based on language and tech stack."""
    config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])
    source_path = Path(source_file)
    stem = source_path.stem
    ext = config.get("file_ext", source_path.suffix)
    
    test_location = tech_stack.get("test_location", "separate-dir") if tech_stack else "separate-dir"
    has_src_dir = tech_stack.get("has_src_dir", False) if tech_stack else False
    is_react = tech_stack.get("is_react", False) if tech_stack else False
    is_nextjs = tech_stack.get("is_nextjs", False) if tech_stack else False

    if language == "python":
        test_filename = f"{config.get('file_prefix', 'test_')}{stem}{ext}"
        test_dir = config["test_dir"]
        if str(source_path.parent) != ".":
            sub_dir = str(source_path.parent).replace("/", "_").replace("\\", "_")
            test_filename = f"test_{sub_dir}_{stem}{ext}"
        return str(Path(test_dir) / test_filename)

    elif language in ("javascript", "typescript"):
        suffix = config.get("file_suffix", ".test")
        test_filename = f"{stem}{suffix}{ext}"
        
        if test_location == "next-to-source":
            return str(source_path.parent / test_filename)
        elif test_location == "mirror-structure":
            if str(source_path.parent).startswith("src"):
                rel_path = source_path.parent
                return str(Path("__tests__") / rel_path / test_filename)
            else:
                return str(Path("__tests__") / test_filename)
        else:
            test_dir = config["test_dir"]
            return str(Path(test_dir) / test_filename)

    elif language == "go":
        test_filename = f"{stem}_test{ext}"
        return str(source_path.parent / test_filename)

    elif language == "java":
        test_filename = f"{stem}Test{ext}"
        test_dir = config["test_dir"]
        pkg_path = str(source_path.parent)
        if pkg_path.startswith("src/main/java"):
            pkg_path = pkg_path.replace("src/main/java", "", 1).lstrip("/")
        return str(Path(test_dir) / pkg_path / test_filename)

    else:
        test_filename = f"test_{stem}{ext}"
        return str(Path("tests") / test_filename)
