import re
import json
import logging
from pathlib import Path
from typing import Dict, Any

from ..ai_service import ai_service
from prompts import prompt_loader
from ..constants import IGNORE_DIRS, SOURCE_EXTENSIONS

logger = logging.getLogger(__name__)


def detect_language(repo_path: str) -> str:
    root = Path(repo_path)
    indicators = {
        "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
        "javascript": ["package.json"],
        "typescript": ["tsconfig.json"],
        "java": ["pom.xml", "build.gradle"],
        "go": ["go.mod"],
        "rust": ["Cargo.toml"],
    }

    for lang, files in indicators.items():
        for f in files:
            if (root / f).exists():
                if lang == "javascript" and (root / "tsconfig.json").exists():
                    return "typescript"
                return lang

    ext_count: Dict[str, int] = {}
    for fp in root.rglob('*'):
        if any(part in IGNORE_DIRS for part in fp.parts):
            continue
        if fp.is_file() and fp.suffix in SOURCE_EXTENSIONS:
            ext_count[fp.suffix] = ext_count.get(fp.suffix, 0) + 1

    ext_to_lang = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.java': 'java', '.go': 'go', '.rs': 'rust',
    }
    if ext_count:
        top_ext = max(ext_count, key=ext_count.get)
        return ext_to_lang.get(top_ext, "python")

    return "python"


def detect_tech_stack(repo_path: str, language: str) -> Dict[str, Any]:
    root = Path(repo_path)

    config_files = {}
    config_patterns = {
        "package.json": "package.json",
        "tsconfig.json": "tsconfig.json",
        "vite.config.ts": "vite.config.*",
        "vite.config.js": "vite.config.*",
        "next.config.js": "next.config.*",
        "next.config.ts": "next.config.*",
        "jest.config.js": "jest.config.*",
        "jest.config.ts": "jest.config.*",
        "vitest.config.ts": "vitest.config.*",
        "vitest.config.js": "vitest.config.*",
        "webpack.config.js": "webpack.config.*",
        "angular.json": "angular.json",
        "vue.config.js": "vue.config.*",
        "nuxt.config.js": "nuxt.config.*",
        "svelte.config.js": "svelte.config.*",
        "requirements.txt": "requirements.txt",
        "pyproject.toml": "pyproject.toml",
        "setup.py": "setup.py",
    }

    for filename in config_patterns.keys():
        filepath = root / filename
        if filepath.exists():
            try:
                content = filepath.read_text(errors='ignore')[:3000]
                config_files[filename] = content
            except Exception:
                pass

    has_src_dir = (root / "src").exists() and (root / "src").is_dir()
    has_app_dir = (root / "app").exists() and (root / "app").is_dir()
    has_pages_dir = (root / "pages").exists() and (root / "pages").is_dir()
    has_components_dir = (root / "components").exists() or ((root / "src" / "components").exists() if has_src_dir else False)

    structure_info = f"""Directory structure:
- Has 'src' directory: {has_src_dir}
- Has 'app' directory: {has_app_dir}
- Has 'pages' directory: {has_pages_dir}
- Has 'components' directory: {has_components_dir}
"""

    if not config_files:
        return {
            "framework": None,
            "test_location": "next-to-source" if has_src_dir and language in ["javascript", "typescript"] else "separate-dir",
            "import_style": "relative" if language in ["javascript", "typescript"] else "absolute",
            "is_react": False,
            "is_nextjs": False,
            "is_vue": False,
            "is_angular": False,
            "has_src_dir": has_src_dir,
        }

    config_text = "\n\n".join([f"### {name}\n```\n{content}\n```" for name, content in config_files.items()])

    prompt = prompt_loader.get_prompt("unit_test_agent.yml", "tech_stack_detection").format(
        structure_info=structure_info,
        config_text=config_text
    )

    try:
        result = ai_service.call_genai(prompt, temperature=0.1, max_tokens=1000, task_name="unit_test_analysis")
        result = result.strip()
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            tech_stack = json.loads(json_match.group())
            tech_stack["has_src_dir"] = has_src_dir
            return tech_stack
    except Exception as e:
        print(f"⚠️ Tech stack detection error: {e}")

    is_react = "react" in str(config_files.get("package.json", "")).lower()
    is_nextjs = "next" in str(config_files.get("package.json", "")).lower()
    is_vue = "vue" in str(config_files.get("package.json", "")).lower()

    return {
        "framework": "next.js" if is_nextjs else ("react" if is_react else ("vue" if is_vue else None)),
        "test_framework": "jest" if language in ["javascript", "typescript"] else "pytest",
        "test_location": "next-to-source" if (is_react or is_nextjs) and has_src_dir else "separate-dir",
        "import_style": "relative",
        "path_alias": None,
        "is_react": is_react,
        "is_nextjs": is_nextjs,
        "is_vue": is_vue,
        "is_angular": False,
        "has_src_dir": has_src_dir,
        "reasoning": "Fallback heuristic detection",
    }
