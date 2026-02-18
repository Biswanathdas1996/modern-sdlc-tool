import os
import re
import json
import subprocess
import shutil
import threading
import uuid
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from .ai_service import ai_service

IGNORE_DIRS = {
    '.git', 'node_modules', '__pycache__', '.next', 'dist', 'build',
    '.venv', 'venv', 'env', '.env', '.idea', '.vscode', 'vendor',
    'target', 'bin', 'obj', '.cache', '.nuxt', '.output', 'coverage',
    '.pytest_cache', '.mypy_cache', 'eggs', '*.egg-info',
}

TEST_DIRS = {'test', 'tests', '__tests__', 'spec', 'specs'}

IGNORE_EXTENSIONS = {
    '.pyc', '.pyo', '.class', '.o', '.so', '.dll', '.exe',
    '.ico', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp',
    '.mp3', '.mp4', '.wav', '.avi', '.mov',
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.woff', '.woff2', '.ttf', '.eot',
    '.lock', '.min.js', '.min.css',
}

SOURCE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
    '.rb', '.php', '.cs', '.cpp', '.c', '.h', '.hpp',
    '.swift', '.kt', '.scala', '.ex', '.exs',
    '.vue', '.svelte',
}

MAX_FILE_SIZE = 100_000
MAX_FILES_FOR_ANALYSIS = 80
MAX_EXISTING_TEST_SAMPLE_SIZE = 6000

LANGUAGE_TEST_CONFIG = {
    "python": {
        "framework": "pytest",
        "test_dir": "tests",
        "file_prefix": "test_",
        "file_ext": ".py",
        "import_style": "from {module} import {name}",
        "test_patterns": [r'^test_.*\.py$', r'.*_test\.py$'],
    },
    "javascript": {
        "framework": "jest",
        "test_dir": "__tests__",
        "file_suffix": ".test",
        "file_ext": ".js",
        "import_style": "const {{ {name} }} = require('{module}');",
        "test_patterns": [r'.*\.test\.js$', r'.*\.spec\.js$', r'^test_.*\.js$'],
    },
    "typescript": {
        "framework": "jest",
        "test_dir": "__tests__",
        "file_suffix": ".test",
        "file_ext": ".ts",
        "import_style": "import {{ {name} }} from '{module}';",
        "test_patterns": [r'.*\.test\.ts$', r'.*\.test\.tsx$', r'.*\.spec\.ts$'],
    },
    "java": {
        "framework": "JUnit 5",
        "test_dir": "src/test/java",
        "file_suffix": "Test",
        "file_ext": ".java",
        "test_patterns": [r'.*Test\.java$', r'.*Tests\.java$', r'.*Spec\.java$'],
    },
    "go": {
        "framework": "testing",
        "test_dir": "",
        "file_suffix": "_test",
        "file_ext": ".go",
        "test_patterns": [r'.*_test\.go$'],
    },
}


class UnitTestAgent:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, Dict[str, Any]] = {}
        print("🧪 Unit Test Generator Agent initialized")

    def _get_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "repo_url": None,
                "repo_path": None,
                "repo_name": None,
                "cloned": False,
                "language": None,
                "tech_stack": None,
                "analysis_cache": {},
                "tests_generated": [],
                "existing_tests": {},
                "test_style_guide": None,
            }
        return self.sessions[session_id]

    def set_repo(self, session_id: str, repo_url: str, repo_path: str, repo_name: str) -> bool:
        session = self._get_session(session_id)
        if session["cloned"]:
            return True

        if not Path(repo_path).exists():
            return False

        language = self._detect_language(repo_path)
        tech_stack = self._detect_tech_stack(repo_path, language)
        session["repo_url"] = repo_url
        session["repo_path"] = repo_path
        session["repo_name"] = repo_name
        session["cloned"] = True
        session["language"] = language
        session["tech_stack"] = tech_stack
        print(f"🧪 Unit Test Agent linked to repo: {repo_name} at {repo_path}")
        print(f"📦 Detected tech stack: {tech_stack}")
        return True

    def _get_file_tree(self, repo_path: str, max_depth: int = 4) -> str:
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

    def _detect_language(self, repo_path: str) -> str:
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

    def _detect_tech_stack(self, repo_path: str, language: str) -> Dict[str, Any]:
        """Use LLM to detect the tech stack and determine test file placement strategy."""
        root = Path(repo_path)
        
        # Collect configuration files
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
        
        # Analyze directory structure
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
            # Return default based on language
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
        
        # Prepare config file contents for LLM
        config_text = "\n\n".join([f"### {name}\n```\n{content}\n```" for name, content in config_files.items()])
        
        prompt = f"""Analyze this project's configuration to determine the tech stack and test file placement strategy.

{structure_info}

Configuration files:
{config_text}

Analyze and return ONLY a JSON object with these fields:
{{
  "framework": "react" | "next.js" | "vue" | "angular" | "node.js" | "express" | "fastapi" | "django" | "flask" | null,
  "test_framework": "jest" | "vitest" | "react-testing-library" | "pytest" | "unittest" | null,
  "test_location": "next-to-source" | "separate-dir" | "mirror-structure",
  "import_style": "relative" | "absolute" | "alias",
  "path_alias": "@" | "~" | null (if using path aliases like @/components),
  "is_react": boolean,
  "is_nextjs": boolean,
  "is_vue": boolean,
  "is_angular": boolean,
  "has_src_dir": boolean,
  "reasoning": "brief explanation"
}}

Guidelines:
- "next-to-source": place test files next to source files (common in React/Next.js)
- "separate-dir": place in dedicated tests directory (common in Python)
- "mirror-structure": mirror source structure in __tests__ directory
- For React/Next.js apps with src directory, prefer "next-to-source"
- Check package.json dependencies for framework detection
- Check for @/ or ~/ aliases in tsconfig or jsconfig

Return ONLY the JSON, no markdown or explanations."""
        
        try:
            result = ai_service.call_genai(prompt, temperature=0.1, max_tokens=1000)
            result = result.strip()
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                tech_stack = json.loads(json_match.group())
                # Set has_src_dir from actual detection
                tech_stack["has_src_dir"] = has_src_dir
                return tech_stack
        except Exception as e:
            print(f"⚠️ Tech stack detection error: {e}")
        
        # Fallback based on simple heuristics
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

    def _collect_source_files(self, repo_path: str) -> Dict[str, str]:
        files = {}
        root = Path(repo_path)

        for fp in root.rglob('*'):
            if any(part in IGNORE_DIRS for part in fp.parts):
                continue
            if any(part in TEST_DIRS for part in fp.parts):
                continue
            if fp.is_file() and fp.suffix in SOURCE_EXTENSIONS:
                if self._is_test_file_strict(fp.name):
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
                    break
        return files

    def _is_test_file_strict(self, filename: str) -> bool:
        lower = filename.lower()
        if re.match(r'^test_.*\.\w+$', lower):
            return True
        if re.match(r'.*_test\.\w+$', lower):
            return True
        if re.match(r'.*\.test\.\w+$', lower):
            return True
        if re.match(r'.*\.spec\.\w+$', lower):
            return True
        if re.match(r'.*Test\.java$', filename):
            return True
        if re.match(r'.*Tests\.java$', filename):
            return True
        return False

    def _is_test_file_by_context(self, filepath: Path, language: str) -> bool:
        parts = set(filepath.parts)
        if parts & TEST_DIRS:
            return True
        if self._is_test_file_strict(filepath.name):
            return True
        config = LANGUAGE_TEST_CONFIG.get(language, {})
        for pattern in config.get("test_patterns", []):
            if re.match(pattern, filepath.name):
                return True
        return False

    def _discover_existing_tests(self, repo_path: str, language: str) -> Dict[str, Dict[str, Any]]:
        existing_tests = {}
        root = Path(repo_path)

        for fp in root.rglob('*'):
            if any(part in IGNORE_DIRS for part in fp.parts):
                continue
            if not fp.is_file():
                continue

            rel_path = fp.relative_to(root)
            is_test = self._is_test_file_by_context(rel_path, language)

            if is_test and fp.suffix in SOURCE_EXTENSIONS:
                try:
                    rel = str(rel_path)
                    content = fp.read_text(errors='ignore')
                    if len(content) > MAX_FILE_SIZE:
                        content = content[:MAX_FILE_SIZE] + "\n... (truncated)"

                    tested_source = self._infer_source_file(rel, language, repo_path)
                    existing_tests[rel] = {
                        "content": content,
                        "size": len(content),
                        "lines": content.count('\n') + 1,
                        "tested_source": tested_source,
                    }
                except Exception:
                    pass

        return existing_tests

    def _infer_source_file(self, test_path: str, language: str, repo_path: str) -> Optional[str]:
        tp = Path(test_path)
        name = tp.stem
        root = Path(repo_path)

        if language == "python":
            source_name = re.sub(r'^test_', '', name)
            source_name = re.sub(r'_test$', '', source_name)
            candidates = []
            candidates.append(f"{source_name}.py")
            candidates.append(f"src/{source_name}.py")
            if '_' in source_name:
                parts = source_name.split('_')
                for i in range(1, len(parts)):
                    dir_part = "/".join(parts[:i])
                    file_part = "_".join(parts[i:])
                    candidates.append(f"{dir_part}/{file_part}.py")
                    candidates.append(f"src/{dir_part}/{file_part}.py")

        elif language in ("javascript", "typescript"):
            ext = ".ts" if language == "typescript" else ".js"
            tsx_ext = ".tsx" if language == "typescript" else ".jsx"
            source_name = re.sub(r'\.(test|spec)$', '', name)
            parent_dir = str(tp.parent)
            mirror_dir = re.sub(r'(^|/)(__tests__|tests?|specs?)(/|$)', r'\1', parent_dir).strip('/')
            candidates = [
                f"src/{source_name}{ext}",
                f"lib/{source_name}{ext}",
                f"{source_name}{ext}",
                f"src/{source_name}{tsx_ext}",
                f"{source_name}{tsx_ext}",
            ]
            if mirror_dir:
                candidates.insert(0, f"{mirror_dir}/{source_name}{ext}")
                candidates.insert(1, f"{mirror_dir}/{source_name}{tsx_ext}")

        elif language == "go":
            source_name = re.sub(r'_test$', '', name)
            candidates = [
                str(tp.parent / f"{source_name}.go"),
            ]

        elif language == "java":
            source_name = re.sub(r'Tests?$', '', name)
            parent_str = str(tp.parent)
            main_path = parent_str.replace("src/test/java", "src/main/java")
            candidates = [
                f"{main_path}/{source_name}.java" if main_path != parent_str else f"{source_name}.java",
                f"src/main/java/{source_name}.java",
                f"{source_name}.java",
            ]

        else:
            source_name = re.sub(r'^test_', '', name)
            candidates = [f"{source_name}{tp.suffix}", f"src/{source_name}{tp.suffix}"]

        for candidate in candidates:
            candidate = candidate.lstrip('/')
            if (root / candidate).exists():
                return candidate

        target_name = candidates[0].split('/')[-1] if candidates else name + tp.suffix
        found = []
        for fp in root.rglob(target_name):
            if any(part in IGNORE_DIRS for part in fp.parts):
                continue
            if any(part in TEST_DIRS for part in fp.parts):
                continue
            if not self._is_test_file_strict(fp.name):
                found.append(str(fp.relative_to(root)))

        if len(found) == 1:
            return found[0]

        return None

    def _analyze_test_patterns(self, existing_tests: Dict[str, Dict[str, Any]], language: str) -> str:
        if not existing_tests:
            return ""

        sample_tests = []
        sorted_tests = sorted(existing_tests.items(), key=lambda x: x[1]["lines"], reverse=True)
        for test_path, test_info in sorted_tests[:2]:
            content = test_info["content"][:MAX_EXISTING_TEST_SAMPLE_SIZE]
            sample_tests.append(f"### File: {test_path}\n```{language}\n{content}\n```")

        samples_text = "\n\n".join(sample_tests)

        prompt = f"""You are a senior {language} test engineer. Analyze these existing test files and extract the testing patterns, conventions, and style used in this project.

{samples_text}

Provide a concise style guide covering:
1. Test framework and assertion library used
2. Naming conventions (test function/method names, describe blocks)
3. Import/require patterns
4. Setup/teardown patterns (fixtures, beforeEach, setUp, etc.)
5. Mocking approach (what library, how mocks are created)
6. File organization (grouping, nesting, describe blocks)
7. Any custom utilities or helpers used
8. Code style (indentation, quotes, semicolons for JS/TS)

Return ONLY the style guide as plain text, no markdown headers. Be concise and specific."""

        try:
            style_guide = ai_service.call_genai(prompt, temperature=0.1, max_tokens=2000)
            return style_guide.strip()
        except Exception as e:
            print(f"⚠️ Test pattern analysis error: {e}")
            return ""

    def _build_coverage_map(
        self,
        source_files: Dict[str, str],
        existing_tests: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        coverage_map = {}

        tested_sources = set()
        source_to_test = {}
        for test_path, test_info in existing_tests.items():
            src = test_info.get("tested_source")
            if src:
                tested_sources.add(src)
                if src not in source_to_test:
                    source_to_test[src] = []
                source_to_test[src].append(test_path)

        for source_path in source_files:
            has_test = source_path in tested_sources
            coverage_map[source_path] = {
                "has_existing_tests": has_test,
                "existing_test_files": source_to_test.get(source_path, []),
            }

        return coverage_map

    def _read_key_files(self, repo_path: str) -> Dict[str, str]:
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

    def _identify_testable_modules(
        self,
        source_files: Dict[str, str],
        language: str,
        coverage_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        file_summaries = []
        for filepath, content in list(source_files.items())[:40]:
            lines = content.count('\n') + 1
            has_tests = coverage_map.get(filepath, {}).get("has_existing_tests", False)
            status = "HAS TESTS" if has_tests else "NO TESTS"
            file_summaries.append(f"- {filepath} ({lines} lines) [{status}]")

        file_list = "\n".join(file_summaries)

        prompt = f"""You are a senior software engineer analyzing a {language} codebase for test coverage gaps.

Given these source files (with their current test coverage status), identify the modules that need tests.

PRIORITIZATION RULES:
1. Files marked [NO TESTS] should be HIGH priority - they have zero test coverage
2. Files marked [HAS TESTS] should be MEDIUM priority - they may need additional coverage for untested functions
3. Skip configuration files, entry points (main.py, index.js, app.py), migration files, and auto-generated code
4. Focus on files with business logic, utility functions, services, and core functionality

Source files:
{file_list}

Return a JSON array of objects, each with:
- "file": the file path
- "priority": "high", "medium", or "low"
- "reason": one-line explanation
- "mode": "new" if [NO TESTS], "augment" if [HAS TESTS]

Return ONLY the JSON array, no other text. Limit to the top 10 most important files."""

        try:
            result = ai_service.call_genai(prompt, temperature=0.1, max_tokens=2000)
            result = result.strip()
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                modules = json.loads(json_match.group())
                valid = [m for m in modules if m.get("file") in source_files]
                for m in valid:
                    if m.get("mode") not in ("new", "augment"):
                        has_tests = coverage_map.get(m["file"], {}).get("has_existing_tests", False)
                        m["mode"] = "augment" if has_tests else "new"
                return valid if valid else self._fallback_modules(source_files, coverage_map)
            return self._fallback_modules(source_files, coverage_map)
        except Exception as e:
            print(f"⚠️ Module identification error: {e}")
            return self._fallback_modules(source_files, coverage_map)

    def _fallback_modules(
        self,
        source_files: Dict[str, str],
        coverage_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        modules = []
        for f in list(source_files.keys())[:10]:
            has_tests = coverage_map.get(f, {}).get("has_existing_tests", False)
            modules.append({
                "file": f,
                "priority": "medium" if has_tests else "high",
                "reason": "Source file",
                "mode": "augment" if has_tests else "new",
            })
        return modules

    def _get_project_deps_context(self, repo_path: str, language: str) -> str:
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

    def _get_related_imports_context(self, filepath: str, content: str, source_files: Dict[str, str], language: str) -> str:
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

    def _get_import_guidance(self, filepath: str, language: str, repo_path: str, tech_stack: Dict[str, Any] = None) -> str:
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
                    # Separate __tests__ directory
                    if has_src_dir and str(source_path).startswith("src/"):
                        # Calculate relative path from __tests__/ to src/
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

    def _check_command_exists(self, command: str) -> bool:
        """Check if a command exists in the system PATH."""
        try:
            if os.name == 'nt':  # Windows
                result = subprocess.run(
                    ["where", command],
                    capture_output=True, text=True, timeout=5
                )
            else:  # Unix/Linux/Mac
                result = subprocess.run(
                    ["which", command],
                    capture_output=True, text=True, timeout=5
                )
            return result.returncode == 0
        except Exception:
            return False

    def _install_test_deps(self, repo_path: str, language: str) -> Dict[str, Any]:
        root = Path(repo_path)
        try:
            if language == "python":
                result = subprocess.run(
                    ["pip", "install", "pytest", "pytest-mock", "-q"],
                    cwd=str(root), capture_output=True, text=True, timeout=120
                )
                req_file = root / "requirements.txt"
                if req_file.exists():
                    try:
                        subprocess.run(
                            ["pip", "install", "-r", "requirements.txt", "-q"],
                            cwd=str(root), capture_output=True, text=True, timeout=180
                        )
                    except Exception:
                        pass
                setup_py = root / "setup.py"
                pyproject = root / "pyproject.toml"
                if setup_py.exists() or pyproject.exists():
                    try:
                        subprocess.run(
                            ["pip", "install", "-e", ".", "-q"],
                            cwd=str(root), capture_output=True, text=True, timeout=180
                        )
                    except Exception:
                        pass
                return {"success": True, "message": "pytest installed"}

            elif language in ("javascript", "typescript"):
                if not self._check_command_exists("npm"):
                    return {
                        "success": False,
                        "message": "npm not found. Please install Node.js from https://nodejs.org/ (includes npm)"
                    }
                
                pkg = root / "package.json"
                if pkg.exists():
                    try:
                        result = subprocess.run(
                            ["npm", "install", "--legacy-peer-deps"],
                            cwd=str(root), capture_output=True, text=True, timeout=300
                        )
                        if result.returncode != 0:
                            print(f"⚠️ npm install warning: {result.stderr[:500]}")
                    except Exception as e:
                        print(f"⚠️ npm install exception: {e}")

                is_cra = self._is_cra_project(str(root))
                if is_cra:
                    test_deps = ["@testing-library/react", "@testing-library/jest-dom", "@testing-library/user-event"]
                    result = subprocess.run(
                        ["npm", "install", "--save-dev", "--legacy-peer-deps"] + test_deps,
                        cwd=str(root), capture_output=True, text=True, timeout=300
                    )
                    if result.returncode != 0:
                        print(f"⚠️ testing-library install warning: {result.stderr[:300]}")
                    return {"success": True, "message": "react-scripts + testing-library installed"}
                else:
                    result = subprocess.run(
                        ["npm", "install", "--save-dev", "jest", "@types/jest"],
                        cwd=str(root), capture_output=True, text=True, timeout=300
                    )
                    if result.returncode != 0:
                        return {"success": False, "message": f"jest install failed: {result.stderr[:500]}"}
                    return {"success": True, "message": "jest installed"}

            elif language == "go":
                result = subprocess.run(
                    ["go", "mod", "tidy"],
                    cwd=str(root), capture_output=True, text=True, timeout=120
                )
                return {"success": True, "message": "go dependencies tidied"}

            return {"success": True, "message": "No specific test deps to install"}
        except subprocess.TimeoutExpired as e:
            print(f"❌ Dependency installation timeout: {e}")
            return {"success": False, "message": "Dependency installation timed out (300s limit). Try manual install."}
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"❌ Dependency installation error: {error_detail}")
            return {"success": False, "message": f"Failed to install deps: {str(e)[:200]}"}

    def _is_cra_project(self, repo_path: str) -> bool:
        pkg_path = Path(repo_path) / "package.json"
        if pkg_path.exists():
            try:
                with open(pkg_path, 'r') as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                return "react-scripts" in deps or "react-scripts test" in scripts.get("test", "")
            except Exception:
                pass
        return False

    def _run_test_file(self, repo_path: str, test_path: str, language: str) -> Dict[str, Any]:
        root = Path(repo_path)
        full_test_path = root / test_path
        if not full_test_path.exists():
            return {"success": False, "passed": False, "output": "Test file not found", "error": "File not found"}

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["CI"] = "true"
        if language == "python":
            env["PYTHONPATH"] = str(root)

        try:
            if language == "python":
                cmd = ["python", "-m", "pytest", test_path, "-v", "--tb=short", "--no-header", "-x"]
            elif language in ("javascript", "typescript"):
                if self._is_cra_project(str(root)):
                    escaped_path = re.escape(test_path).replace("\\\\", "/")
                    cmd = ["npx", "react-scripts", "test", "--watchAll=false", "--ci", "--verbose", "--forceExit", "--testPathPattern", escaped_path]
                else:
                    cmd = ["npx", "jest", test_path, "--no-coverage", "--verbose", "--forceExit"]
            elif language == "go":
                test_dir = str(Path(test_path).parent)
                if test_dir == ".":
                    test_dir = "./"
                else:
                    test_dir = "./" + test_dir + "/..."
                cmd = ["go", "test", "-v", "-count=1", test_dir]
            else:
                return {"success": True, "passed": True, "output": "No runner for this language, skipping validation"}

            result = subprocess.run(
                cmd, cwd=str(root), capture_output=True, text=True,
                timeout=180, env=env
            )

            combined_output = result.stdout + "\n" + result.stderr
            combined_output = combined_output[-4000:]

            if result.returncode != 0 and self._is_cra_project(str(root)) and "react-scripts" in " ".join(cmd):
                if "Cannot find module" in combined_output and "react-scripts" in combined_output:
                    print("⚠️ react-scripts test failed, falling back to npx jest")
                    fallback_cmd = ["npx", "jest", test_path, "--no-coverage", "--verbose", "--forceExit"]
                    result = subprocess.run(
                        fallback_cmd, cwd=str(root), capture_output=True, text=True,
                        timeout=180, env=env
                    )
                    combined_output = result.stdout + "\n" + result.stderr
                    combined_output = combined_output[-4000:]

            passed = result.returncode == 0

            return {
                "success": True,
                "passed": passed,
                "output": combined_output,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": True, "passed": False, "output": "Test execution timed out (180s)", "returncode": -1}
        except Exception as e:
            print(f"⚠️ Test execution error: {e}")
            return {"success": False, "passed": False, "output": str(e), "returncode": -1}

    def _extract_passing_tests_only(
        self,
        filepath: str,
        source_content: str,
        test_code: str,
        error_output: str,
        language: str,
    ) -> Dict[str, Any]:
        prompt = f"""You are a senior {language} developer. A test file has some passing tests and some failing tests.
Your task: REMOVE the failing tests and KEEP ONLY the passing tests. Return a valid, runnable test file.

SOURCE FILE ({filepath}):
```{language}
{source_content[:4000]}
```

CURRENT TEST CODE (has some failing tests):
```{language}
{test_code[:6000]}
```

TEST ERROR OUTPUT (shows which tests fail and why):
```
{error_output[:3000]}
```

RULES:
1. Carefully read the error output to identify EXACTLY which test functions/cases FAIL
2. REMOVE every failing test function/case entirely
3. KEEP all passing tests exactly as they are - do not modify them
4. KEEP all necessary imports, setup, and teardown that the passing tests need
5. If ALL tests are failing, return ONLY the imports and an empty test class/describe block with a single trivial test that just asserts true
6. The result must be a complete, runnable test file
7. Do NOT add new tests - only keep existing passing ones

Return ONLY the complete test file code with only passing tests. No explanations, no markdown fences."""

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

    def _get_mocking_guidance(self, language: str) -> str:
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

    def _fix_failing_tests(
        self,
        filepath: str,
        source_content: str,
        test_code: str,
        error_output: str,
        language: str,
        attempt: int,
        deps_context: str = "",
        repo_path: str = "",
    ) -> Dict[str, Any]:
        config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])

        is_cra = self._is_cra_project(repo_path) if repo_path else False
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

        prompt = f"""You are a senior {language} developer fixing failing unit tests. This is fix attempt {attempt}.

The test file was generated for this source file but FAILED when executed. Fix the tests so they PASS.

SOURCE FILE ({filepath}):
```{language}
{source_content[:6000]}
```

FAILING TEST CODE:
```{language}
{test_code[:6000]}
```

TEST EXECUTION ERROR OUTPUT:
```
{error_output[:3000]}
```

{f"PROJECT DEPENDENCIES:{deps_context}" if deps_context else ""}
{cra_note}
CRITICAL FIX RULES:
1. Carefully read the error output to understand EXACTLY why each test failed
2. Common issues to fix:
   - ImportError/ModuleNotFoundError: Fix import paths, use correct module structure, mock unavailable modules
   - AttributeError: The function/class doesn't exist as assumed - check the source carefully
   - AssertionError: Expected values are wrong - analyze the actual source code logic
   - TypeError: Wrong argument count or types - match the actual function signatures
   - SyntaxError in JSX: Make sure test files that test React components have proper JSX support
   - Cannot find module: Verify the relative import path from the test file to the source file
3. MOCK all external dependencies (database connections, API calls, file system, network requests)
{self._get_mocking_guidance(language)}
5. DO NOT test private/internal methods unless they're the only methods
6. Make sure import paths exactly match the project structure
7. If a function is too complex to test reliably, write a simpler test that just validates basic behavior
8. REMOVE any test that cannot be reliably fixed rather than leaving it broken
9. If attempt >= 2, be MORE AGGRESSIVE about removing problematic tests - keep only tests you are CONFIDENT will pass

Return ONLY the complete fixed test file code. No explanations, no markdown fences."""

        try:
            fixed_code = ai_service.call_genai(prompt, temperature=0.15, max_tokens=8192)
            fixed_code = fixed_code.strip()
            if fixed_code.startswith("```"):
                lines = fixed_code.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                fixed_code = "\n".join(lines)
            return {"success": True, "test_code": fixed_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_tests_for_file(
        self,
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

        import_guidance = self._get_import_guidance(filepath, language, repo_path, tech_stack)
        
        is_cra = self._is_cra_project(repo_path)
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
            prompt = f"""You are a senior {language} developer improving test coverage.

This source file already has tests. Your job is to INCREASE COVERAGE by adding ONLY NEW test cases that are NOT already covered.

Source file: {filepath}
```{language}
{content[:8000]}
```

Existing test file:
```{language}
{existing_test_content[:6000]}
```
{style_section}{deps_section}{imports_section}{import_section}
CRITICAL RULES:
1. Analyze the existing tests carefully - understand what is ALREADY tested
2. Identify functions, methods, branches, and edge cases that are NOT covered
3. Generate ONLY the new test functions/methods that need to be ADDED
4. DO NOT duplicate any existing test - no overlapping test names or scenarios
5. Follow the EXACT same coding style, naming conventions, and patterns as the existing tests
6. Follow the import guidelines above - use correct import paths based on project structure
7. Focus on: untested functions, missing edge cases, error paths, boundary conditions
8. MOCK all external dependencies (database, API calls, file I/O, network) - do NOT rely on real connections
9. Make sure every test can run independently without any external service

Return the COMPLETE UPDATED test file that includes both the existing tests AND the new tests integrated together.
The code must be ready to save to a file and run. Return ONLY the code, no explanations or markdown."""

        else:
            prompt = f"""You are a senior {language} developer writing comprehensive unit tests.

Analyze this source file and generate thorough unit tests using {config['framework']}.

File: {filepath}
```{language}
{content[:8000]}
```
{style_section}{deps_section}{imports_section}{import_section}
Requirements:
1. Write tests for EVERY public function, class method, and key behavior
2. Include positive tests (happy path), negative tests (error cases), and edge cases
3. MOCK ALL external dependencies (API calls, database, file I/O, network requests) - tests MUST run without any external service
4. Use unittest.mock.patch / pytest-mock for Python, jest.mock for JavaScript/TypeScript
5. Follow {config['framework']} best practices and conventions
6. Add descriptive test names that explain what is being tested
7. Group related tests in test classes/describe blocks where appropriate
8. Test boundary conditions and special cases
9. Follow the import guidelines above - use correct import paths based on project structure
10. Every test must be self-contained and deterministic - no reliance on external state

Return ONLY the complete test file code, no explanations or markdown. The code must be ready to save to a file and run."""

        try:
            test_code = ai_service.call_genai(prompt, temperature=0.2, max_tokens=8192)
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

    def _determine_test_path(self, source_file: str, language: str, repo_path: str, tech_stack: Dict[str, Any] = None) -> str:
        """Determine test file path based on language and tech stack."""
        config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])
        source_path = Path(source_file)
        stem = source_path.stem
        ext = config.get("file_ext", source_path.suffix)
        
        # Get tech stack info
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
            
            # For React/Next.js apps, place tests next to source files
            if test_location == "next-to-source":
                # If source is in src/, place test there too
                return str(source_path.parent / test_filename)
            elif test_location == "mirror-structure":
                # Mirror the source structure in __tests__
                if str(source_path.parent).startswith("src"):
                    # Keep the structure after src/
                    rel_path = source_path.parent
                    return str(Path("__tests__") / rel_path / test_filename)
                else:
                    return str(Path("__tests__") / test_filename)
            else:
                # Default: separate __tests__ directory
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

    def _write_test_file(self, repo_path: str, test_path: str, test_code: str) -> Dict[str, Any]:
        try:
            full_path = Path(repo_path) / test_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(test_code, encoding='utf-8')
            return {"success": True, "path": test_path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": test_path}

    def _write_test_config(self, repo_path: str, language: str):
        root = Path(repo_path)
        if language == "python":
            conftest = root / "tests" / "conftest.py"
            if not conftest.exists():
                conftest.parent.mkdir(parents=True, exist_ok=True)
                conftest.write_text("", encoding='utf-8')
            init = root / "tests" / "__init__.py"
            if not init.exists():
                init.write_text("", encoding='utf-8')

    def _detect_intent(self, query: str) -> str:
        q = query.lower()
        if any(k in q for k in ['generate', 'write', 'create', 'unit test', 'test case', 'test']):
            return 'generate'
        if any(k in q for k in ['status', 'progress', 'how many', 'what tests']):
            return 'status'
        return 'general'

    def process_query(self, query: str, session_id: str) -> Dict[str, Any]:
        session = self._get_session(session_id)
        thinking_steps = []
        intent = self._detect_intent(query)

        if not session["cloned"]:
            return {
                "success": True,
                "response": "I need a repository to work with first. Please go to the **Analyze Repository** page (Step 1 in the sidebar) and analyze a GitHub repository. Once that's done, come back here and I'll be able to generate unit tests for it.\n\nIf you've already analyzed a repo, try refreshing this page.",
                "thinking_steps": thinking_steps,
            }

        repo_path = session["repo_path"]
        language = session["language"]

        if intent == 'generate' or intent == 'general':
            task_id = str(uuid.uuid4())
            self.tasks[task_id] = {
                "status": "running",
                "thinking_steps": [
                    {"type": "tool_call", "content": "Scanning repository for existing tests", "tool_name": "discover_tests"}
                ],
                "response": None,
                "success": None,
                "session_id": session_id,
                "progress": "Scanning for existing tests...",
                "task_id": task_id,
            }

            thread = threading.Thread(
                target=self._run_generate_task,
                args=(task_id, session_id, repo_path, language),
                daemon=True,
            )
            thread.start()

            return {
                "success": True,
                "response": "Starting intelligent test generation with validation...\n\nHere's what I'll do:\n1. Scan for existing tests and learn your project's testing patterns\n2. Identify coverage gaps and generate new tests\n3. **Run each test file to verify it passes**\n4. **Auto-fix any failing tests** (up to 3 attempts per file)\n5. Only keep tests that are 100% passing\n\nThis may take several minutes since every test is validated by actually running it.",
                "thinking_steps": thinking_steps,
                "task_id": task_id,
            }

        if intent == 'status':
            if session["tests_generated"]:
                response = f"**Tests generated so far:** {len(session['tests_generated'])}\n\n"
                for t in session["tests_generated"]:
                    mode_label = "updated" if t.get("mode") == "augment" else "new"
                    response += f"- `{t['test_path']}` ({mode_label}, from `{t['source_file']}`)\n"
                response += "\nSay **\"push to GitHub\"** to push these tests to a new branch."
            else:
                response = "No tests generated yet. Say **\"generate tests\"** to get started."
            return {
                "success": True,
                "response": response,
                "thinking_steps": thinking_steps,
            }

        return {
            "success": True,
            "response": "I can help you with:\n- **Generate tests**: analyze the codebase and create unit tests\n- **Check status**: see what tests have been generated\n\nFor cloning repos and pushing code, use the **GitHub Agent**.\n\nWhat would you like to do?",
            "thinking_steps": thinking_steps,
        }

    def _run_generate_task(self, task_id: str, session_id: str, repo_path: str, language: str):
        task = self.tasks[task_id]
        session = self._get_session(session_id)
        MAX_FIX_ATTEMPTS = 2
        TIME_BUDGET_SECONDS = 15 * 60
        start_time = time.time()

        try:
            existing_tests = self._discover_existing_tests(repo_path, language)
            session["existing_tests"] = existing_tests
            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"Found {len(existing_tests)} existing test files" if existing_tests else "No existing tests found - will create from scratch"
            })
            task["progress"] = f"Found {len(existing_tests)} existing test files"

            style_guide = ""
            if existing_tests:
                task["thinking_steps"].append({
                    "type": "tool_call",
                    "content": f"Analyzing testing patterns from {min(2, len(existing_tests))} sample test files",
                    "tool_name": "analyze_patterns"
                })
                task["progress"] = "Analyzing existing test patterns..."

                style_guide = self._analyze_test_patterns(existing_tests, language)
                session["test_style_guide"] = style_guide

                if style_guide:
                    task["thinking_steps"].append({
                        "type": "tool_result",
                        "content": "Extracted testing style guide from existing tests"
                    })
                else:
                    task["thinking_steps"].append({
                        "type": "tool_result",
                        "content": "Could not extract patterns, will use framework defaults"
                    })

            task["thinking_steps"].append({
                "type": "tool_call",
                "content": "Collecting source files for analysis",
                "tool_name": "collect_sources"
            })
            task["progress"] = "Collecting source files..."

            source_files = self._collect_source_files(repo_path)
            task["thinking_steps"].append({"type": "tool_result", "content": f"Found {len(source_files)} source files"})
            task["progress"] = f"Found {len(source_files)} source files"

            if not source_files:
                task["status"] = "completed"
                task["success"] = False
                task["response"] = "No source files found in the repository to generate tests for."
                return

            deps_context = self._get_project_deps_context(repo_path, language)

            coverage_map = self._build_coverage_map(source_files, existing_tests)
            covered_count = sum(1 for v in coverage_map.values() if v["has_existing_tests"])
            uncovered_count = len(coverage_map) - covered_count

            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"Coverage analysis: {covered_count} files with tests, {uncovered_count} files without tests"
            })

            task["thinking_steps"].append({
                "type": "tool_call",
                "content": "Identifying testable modules and coverage gaps",
                "tool_name": "identify_modules"
            })
            task["progress"] = "Identifying coverage gaps..."

            testable_modules = self._identify_testable_modules(source_files, language, coverage_map)
            task["thinking_steps"].append({"type": "tool_result", "content": f"Identified {len(testable_modules)} modules to process"})
            task["progress"] = f"Identified {len(testable_modules)} modules to process"

            self._write_test_config(repo_path, language)

            task["thinking_steps"].append({
                "type": "tool_call",
                "content": "Installing test dependencies",
                "tool_name": "install_deps"
            })
            task["progress"] = "Installing test dependencies..."
            deps_result = self._install_test_deps(repo_path, language)
            deps_installed = deps_result.get("success", False)
            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"Dependencies: {deps_result['message']}"
            })
            if not deps_installed:
                print(f"⚠️ Dependency installation failed for {repo_path}: {deps_result['message']}")
                task["thinking_steps"].append({
                    "type": "tool_result",
                    "content": f"⚠️ Dependency installation failed - tests will be generated but validation will be skipped\nReason: {deps_result['message']}"
                })

            generated_tests = []
            augmented_tests = []
            failed_tests = []

            for i, module in enumerate(testable_modules):
                elapsed = time.time() - start_time
                remaining = TIME_BUDGET_SECONDS - elapsed
                if remaining < 60:
                    task["thinking_steps"].append({
                        "type": "tool_result",
                        "content": f"⏱️ Time budget reached ({int(elapsed)}s elapsed). Processed {i}/{len(testable_modules)} modules."
                    })
                    break

                filepath = module["file"]
                if filepath not in source_files:
                    continue

                mode = module.get("mode", "new")
                mode_label = "Augmenting" if mode == "augment" else "Generating"

                task["thinking_steps"].append({
                    "type": "tool_call",
                    "content": f"[{i+1}/{len(testable_modules)}] {mode_label} tests for: {filepath}",
                    "tool_name": "generate_test"
                })
                task["progress"] = f"{mode_label} tests [{i+1}/{len(testable_modules)}]: {filepath}"

                content = source_files[filepath]

                imports_context = self._get_related_imports_context(filepath, content, source_files, language)

                existing_test_content = ""
                augment_test_path = None
                if mode == "augment":
                    test_files = coverage_map.get(filepath, {}).get("existing_test_files", [])
                    for tf in test_files:
                        if tf in existing_tests:
                            existing_test_content = existing_tests[tf]["content"]
                            augment_test_path = tf
                            break
                    if not existing_test_content:
                        mode = "new"

                test_result = self._generate_tests_for_file(
                    filepath, content, language, repo_path,
                    style_guide=style_guide,
                    existing_test_content=existing_test_content,
                    mode=mode,
                    deps_context=deps_context,
                    imports_context=imports_context,
                    tech_stack=session.get("tech_stack"),
                )

                if test_result["success"]:
                    if mode == "augment" and augment_test_path:
                        test_path = augment_test_path
                    else:
                        test_path = self._determine_test_path(filepath, language, repo_path, session.get("tech_stack"))

                    write_result = self._write_test_file(repo_path, test_path, test_result["test_code"])

                    if write_result["success"]:
                        if not deps_installed:
                            actual_mode = test_result.get("mode", mode)
                            entry = {
                                "source_file": filepath,
                                "test_path": test_path,
                                "priority": module.get("priority", "medium"),
                                "mode": actual_mode,
                                "validated": False,
                                "fix_attempts": 0,
                            }
                            if actual_mode == "augment":
                                augmented_tests.append(entry)
                            else:
                                generated_tests.append(entry)
                            action = "Updated" if actual_mode == "augment" else "Created"
                            task["thinking_steps"].append({
                                "type": "tool_result",
                                "content": f"✅ {action}: {test_path} (validation skipped - deps not installed)"
                            })
                            continue

                        task["thinking_steps"].append({
                            "type": "tool_call",
                            "content": f"Running tests to validate: {test_path}",
                            "tool_name": "run_test"
                        })
                        task["progress"] = f"Validating tests [{i+1}/{len(testable_modules)}]: {test_path}"

                        current_test_code = test_result["test_code"]
                        test_passed = False
                        fix_attempts = 0
                        error_output = ""

                        run_result = self._run_test_file(repo_path, test_path, language)

                        if run_result.get("passed"):
                            test_passed = True
                            task["thinking_steps"].append({
                                "type": "tool_result",
                                "content": f"✅ Tests PASSED on first run: {test_path}"
                            })
                        else:
                            error_output = run_result.get("output", "Unknown error")
                            fix_time_remaining = TIME_BUDGET_SECONDS - (time.time() - start_time)
                            if fix_time_remaining < 90:
                                task["thinking_steps"].append({
                                    "type": "tool_result",
                                    "content": f"⚠️ Tests failed but time budget low - skipping fix attempts for {test_path}"
                                })
                                actual_mode = test_result.get("mode", mode)
                                entry = {
                                    "source_file": filepath,
                                    "test_path": test_path,
                                    "priority": module.get("priority", "medium"),
                                    "mode": actual_mode,
                                    "validated": False,
                                    "fix_attempts": 0,
                                }
                                if actual_mode == "augment":
                                    augmented_tests.append(entry)
                                else:
                                    generated_tests.append(entry)
                                continue

                            task["thinking_steps"].append({
                                "type": "tool_result",
                                "content": f"⚠️ Tests failed, attempting AI-powered fix (attempt 1/{MAX_FIX_ATTEMPTS})"
                            })

                            while not test_passed and fix_attempts < MAX_FIX_ATTEMPTS:
                                fix_attempts += 1
                                task["progress"] = f"Fixing tests [{i+1}/{len(testable_modules)}] (attempt {fix_attempts}/{MAX_FIX_ATTEMPTS}): {filepath}"

                                task["thinking_steps"].append({
                                    "type": "tool_call",
                                    "content": f"AI fixing test failures (attempt {fix_attempts}/{MAX_FIX_ATTEMPTS})",
                                    "tool_name": "fix_test"
                                })

                                fix_result = self._fix_failing_tests(
                                    filepath, content, current_test_code,
                                    error_output, language, fix_attempts,
                                    deps_context=deps_context,
                                    repo_path=repo_path,
                                )

                                if fix_result["success"]:
                                    current_test_code = fix_result["test_code"]
                                    self._write_test_file(repo_path, test_path, current_test_code)

                                    rerun = self._run_test_file(repo_path, test_path, language)
                                    if rerun.get("passed"):
                                        test_passed = True
                                        task["thinking_steps"].append({
                                            "type": "tool_result",
                                            "content": f"✅ Tests PASSED after fix attempt {fix_attempts}"
                                        })
                                    else:
                                        error_output = rerun.get("output", "Unknown error")
                                        task["thinking_steps"].append({
                                            "type": "tool_result",
                                            "content": f"⚠️ Tests still failing after attempt {fix_attempts}"
                                        })
                                else:
                                    task["thinking_steps"].append({
                                        "type": "tool_result",
                                        "content": f"⚠️ AI fix failed: {fix_result.get('error', 'unknown')}"
                                    })
                                    break

                        actual_mode = test_result.get("mode", mode)

                        if not test_passed and fix_attempts >= MAX_FIX_ATTEMPTS:
                            task["thinking_steps"].append({
                                "type": "tool_call",
                                "content": f"Extracting only passing tests from {test_path}",
                                "tool_name": "extract_passing"
                            })
                            task["progress"] = f"Extracting passing tests [{i+1}/{len(testable_modules)}]: {filepath}"

                            extract_result = self._extract_passing_tests_only(
                                filepath, content, current_test_code,
                                error_output, language,
                            )

                            if extract_result["success"]:
                                cleaned_code = extract_result["test_code"]
                                self._write_test_file(repo_path, test_path, cleaned_code)
                                verify_run = self._run_test_file(repo_path, test_path, language)
                                if verify_run.get("passed"):
                                    test_passed = True
                                    current_test_code = cleaned_code
                                    task["thinking_steps"].append({
                                        "type": "tool_result",
                                        "content": f"✅ Kept only passing tests in {test_path} (removed failing ones)"
                                    })
                                else:
                                    task["thinking_steps"].append({
                                        "type": "tool_result",
                                        "content": f"⚠️ Extracted tests still failing - will remove file"
                                    })

                        entry = {
                            "source_file": filepath,
                            "test_path": test_path,
                            "priority": module.get("priority", "medium"),
                            "mode": actual_mode,
                            "validated": test_passed,
                            "fix_attempts": fix_attempts,
                        }

                        if actual_mode == "augment":
                            augmented_tests.append(entry)
                        else:
                            generated_tests.append(entry)

                        if not test_passed:
                            task["thinking_steps"].append({
                                "type": "tool_result",
                                "content": f"⚠️ Kept {test_path} (not all tests passing after {fix_attempts} fix attempts - file preserved for manual review)"
                            })
                    else:
                        failed_tests.append({"file": filepath, "error": write_result["error"]})
                        task["thinking_steps"].append({
                            "type": "tool_result",
                            "content": f"❌ Failed to write: {test_path} - {write_result['error']}"
                        })
                else:
                    failed_tests.append({"file": filepath, "error": test_result["error"]})
                    task["thinking_steps"].append({
                        "type": "tool_result",
                        "content": f"❌ Failed to generate tests for: {filepath}"
                    })

            session["tests_generated"] = generated_tests + augmented_tests

            config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])
            all_tests = generated_tests + augmented_tests
            validated_count = sum(1 for t in all_tests if t.get("validated"))
            unvalidated_count = sum(1 for t in all_tests if not t.get("validated"))
            total_count = len(all_tests)

            response = f"## Unit Test Generation Complete\n\n"
            response += f"**Repository:** {session['repo_name']}\n"
            response += f"**Language:** {language.title()} | **Framework:** {config['framework']}\n"
            if unvalidated_count == 0 and validated_count > 0:
                response += f"**All {validated_count} test files validated - 100% passing** ✅\n\n"
            elif validated_count > 0:
                response += f"**{validated_count}/{total_count} test files validated and passing** ✅\n\n"
            else:
                response += f"**{total_count} test files generated**\n\n"
                if not deps_installed and "npm not found" in deps_result.get('message', ''):
                    response += f"⚠️ **Tests not validated** - npm not installed. Install Node.js from https://nodejs.org/ then regenerate tests.\n\n"

            if existing_tests:
                response += f"**Existing tests found:** {len(existing_tests)} files (patterns analyzed and followed)\n\n"

            if generated_tests:
                response += f"### ✅ New Test Files Created: {len(generated_tests)}\n\n"
                response += "| Source File | Test File | Priority | Status |\n"
                response += "|---|---|---|---|\n"
                for t in generated_tests:
                    if t.get("validated"):
                        fix_note = f" (fixed in {t['fix_attempts']} attempt{'s' if t['fix_attempts'] != 1 else ''})" if t.get('fix_attempts', 0) > 0 else ""
                        status = f"✅ Passing{fix_note}"
                    elif t.get("fix_attempts", 0) > 0:
                        status = f"⚠️ Needs review (kept after {t['fix_attempts']} fix attempts)"
                    else:
                        status = "⚠️ Not validated"
                    response += f"| `{t['source_file']}` | `{t['test_path']}` | {t['priority']} | {status} |\n"
                response += "\n"

            if augmented_tests:
                response += f"### 🔄 Existing Tests Updated: {len(augmented_tests)}\n\n"
                response += "| Source File | Test File | Priority | Status |\n"
                response += "|---|---|---|---|\n"
                for t in augmented_tests:
                    if t.get("validated"):
                        fix_note = f" (fixed in {t['fix_attempts']} attempt{'s' if t['fix_attempts'] != 1 else ''})" if t.get('fix_attempts', 0) > 0 else ""
                        status = f"✅ Passing{fix_note}"
                    elif t.get("fix_attempts", 0) > 0:
                        status = f"⚠️ Needs review (kept after {t['fix_attempts']} fix attempts)"
                    else:
                        status = "⚠️ Not validated"
                    response += f"| `{t['source_file']}` | `{t['test_path']}` | {t['priority']} | {status} |\n"
                response += "\n"

            if failed_tests:
                response += f"### ⚠️ Could Not Generate Passing Tests: {len(failed_tests)} files\n\n"
                for f in failed_tests:
                    response += f"- `{f['file']}`: {f.get('error', 'Unknown error')}\n"
                response += "\n*These files could not be generated. Source files that had tests generated but with some failures are preserved for manual review.*\n\n"

            if generated_tests or augmented_tests:
                if validated_count > 0 and unvalidated_count == 0:
                    response += (
                        "---\n\n"
                        "**Every test file has been executed and verified to pass.** "
                    )
                else:
                    response += "---\n\n"
                response += (
                    "Say **\"push to GitHub\"** to push these tests to a new branch on your repository. "
                    "The GitHub Agent will handle the push for you.\n\n"
                    "You can also ask me to regenerate tests for specific files."
                )

            task["status"] = "completed"
            task["success"] = True
            task["response"] = response
            task["progress"] = "Complete"

        except Exception as e:
            print(f"❌ Task {task_id} error: {e}")
            import traceback
            traceback.print_exc()
            task["status"] = "completed"
            task["success"] = False
            task["response"] = f"An error occurred during test generation: {str(e)}"
            task["progress"] = "Error"

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.tasks.get(task_id)
        if not task:
            return None
        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": task.get("progress", ""),
            "thinking_steps": task.get("thinking_steps", []),
            "response": task.get("response"),
            "success": task.get("success"),
        }


unit_test_agent = UnitTestAgent()
