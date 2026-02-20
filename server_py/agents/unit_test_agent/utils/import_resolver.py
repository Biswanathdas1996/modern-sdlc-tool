import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def calculate_correct_import_path(test_file_path: str, source_file_path: str, tech_stack: Dict[str, Any] = None) -> str:
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


def get_import_guidance(filepath: str, language: str, repo_path: str, tech_stack: Optional[Dict[str, Any]] = None) -> str:
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
