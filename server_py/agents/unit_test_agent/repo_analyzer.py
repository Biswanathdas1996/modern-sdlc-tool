import re
import json
from pathlib import Path
from typing import Dict, Any

from .ai_service import ai_service
from prompts import prompt_loader
from .constants import (
    logger, IGNORE_DIRS, TEST_DIRS, IGNORE_EXTENSIONS,
    SOURCE_EXTENSIONS, MAX_FILE_SIZE, MAX_FILES_FOR_ANALYSIS,
)
from .test_discovery import is_test_file_strict


def get_file_tree(repo_path: str, max_depth: int = 4) -> str:
    tree_lines = []
    root = Path(repo_path)

    def walk(path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        all_ignore = IGNORE_DIRS - TEST_DIRS
        dirs = [e for e in entries if e.is_dir() and e.name not in all_ignore and not e.name.startswith('.')]
        files = [e for e in entries if e.is_file() and e.suffix not in IGNORE_EXTENSIONS]

        for i, d in enumerate(dirs):
            connector = "└── " if i == len(dirs) - 1 and not files else "├── "
            tree_lines.append(f"{prefix}{connector}{d.name}/")
            ext = "    " if i == len(dirs) - 1 and not files else "│   "
            walk(d, prefix + ext, depth + 1)

        for i, f in enumerate(files[:30]):
            connector = "└── " if i == len(files[:30]) - 1 else "├── "
            tree_lines.append(f"{prefix}{connector}{f.name}")
        if len(files) > 30:
            tree_lines.append(f"{prefix}└── ... ({len(files) - 30} more files)")

    walk(root)
    return "\n".join(tree_lines[:500])


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
    """Use LLM to detect the tech stack and determine test file placement strategy."""
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
        result = ai_service.call_genai(prompt, temperature=0.1, max_tokens=1000)
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


def collect_source_files(repo_path: str) -> Dict[str, str]:
    logger.info(f"Collecting source files from: {repo_path}")
    files = {}
    root = Path(repo_path)

    for fp in root.rglob('*'):
        if any(part in IGNORE_DIRS for part in fp.parts):
            continue
        if any(part in TEST_DIRS for part in fp.parts):
            continue
        if fp.is_file() and fp.suffix in SOURCE_EXTENSIONS:
            if is_test_file_strict(fp.name):
                continue
            rel = str(fp.relative_to(root))
            try:
                text = fp.read_text(errors='ignore')
                if len(text) > MAX_FILE_SIZE:
                    text = text[:MAX_FILE_SIZE] + "\n... (truncated)"
                files[rel] = text
            except Exception:
                pass
            if len(files) >= MAX_FILES_FOR_ANALYSIS:
                logger.info(f"Reached maximum file limit ({MAX_FILES_FOR_ANALYSIS}), stopping collection")
                break
    logger.info(f"Collected {len(files)} source files")
    return files


def read_key_files(repo_path: str) -> Dict[str, str]:
    key_files = [
        "README.md", "readme.md",
        "package.json", "requirements.txt", "pyproject.toml",
        "pom.xml", "build.gradle", "go.mod", "Cargo.toml",
        "setup.py", "setup.cfg",
    ]
    contents = {}
    root = Path(repo_path)
    for kf in key_files:
        fp = root / kf
        if fp.exists() and fp.is_file():
            try:
                text = fp.read_text(errors='ignore')
                if len(text) > MAX_FILE_SIZE:
                    text = text[:MAX_FILE_SIZE] + "\n... (truncated)"
                contents[kf] = text
            except Exception:
                pass
    return contents


def get_project_deps_context(repo_path: str, language: str) -> str:
    root = Path(repo_path)
    deps_info = ""
    if language == "python":
        for dep_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
            fp = root / dep_file
            if fp.exists():
                try:
                    text = fp.read_text(errors='ignore')[:3000]
                    deps_info += f"\n{dep_file}:\n{text}\n"
                except Exception:
                    pass
    elif language in ("javascript", "typescript"):
        pkg = root / "package.json"
        if pkg.exists():
            try:
                text = pkg.read_text(errors='ignore')[:3000]
                deps_info += f"\npackage.json:\n{text}\n"
            except Exception:
                pass
    elif language == "go":
        mod = root / "go.mod"
        if mod.exists():
            try:
                text = mod.read_text(errors='ignore')[:3000]
                deps_info += f"\ngo.mod:\n{text}\n"
            except Exception:
                pass
    return deps_info


def get_related_imports_context(filepath: str, content: str, source_files: Dict[str, str], language: str) -> str:
    imported_files = []
    if language == "python":
        for match in re.finditer(r'(?:from|import)\s+([\w.]+)', content):
            mod = match.group(1).replace('.', '/')
            candidates = [f"{mod}.py", f"{mod}/__init__.py"]
            for c in candidates:
                if c in source_files:
                    imported_files.append(c)
                    break
    elif language in ("javascript", "typescript"):
        for match in re.finditer(r'(?:require|from)\s*[(\s]["\']([./][^"\']+)', content):
            mod = match.group(1)
            for ext in ['.js', '.ts', '.jsx', '.tsx', '']:
                candidate = mod + ext
                candidate = str(Path(filepath).parent / candidate) if mod.startswith('.') else candidate
                normalized = str(Path(candidate))
                if normalized in source_files:
                    imported_files.append(normalized)
                    break

    context = ""
    for imp_file in imported_files[:3]:
        imp_content = source_files[imp_file][:2000]
        context += f"\nImported module ({imp_file}):\n```\n{imp_content}\n```\n"
    return context
