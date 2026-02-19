import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from .ai_service import ai_service
from prompts import prompt_loader
from .constants import (
    logger, IGNORE_DIRS, TEST_DIRS, SOURCE_EXTENSIONS,
    MAX_FILE_SIZE, LANGUAGE_TEST_CONFIG, MAX_EXISTING_TEST_SAMPLE_SIZE,
)


def is_test_file_strict(filename: str) -> bool:
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


def is_test_file_by_context(filepath: Path, language: str) -> bool:
    parts = set(filepath.parts)
    if parts & TEST_DIRS:
        return True
    if is_test_file_strict(filepath.name):
        return True
    config = LANGUAGE_TEST_CONFIG.get(language, {})
    for pattern in config.get("test_patterns", []):
        if re.match(pattern, filepath.name):
            return True
    return False


def discover_existing_tests(repo_path: str, language: str) -> Dict[str, Dict[str, Any]]:
    logger.info(f"Discovering existing tests in: {repo_path}")
    existing_tests = {}
    root = Path(repo_path)

    for fp in root.rglob('*'):
        if any(part in IGNORE_DIRS for part in fp.parts):
            continue
        if not fp.is_file():
            continue

        rel_path = fp.relative_to(root)
        is_test = is_test_file_by_context(rel_path, language)

        if is_test and fp.suffix in SOURCE_EXTENSIONS:
            try:
                rel = str(rel_path)
                content = fp.read_text(errors='ignore')
                if len(content) > MAX_FILE_SIZE:
                    content = content[:MAX_FILE_SIZE] + "\n... (truncated)"

                tested_source = infer_source_file(rel, language, repo_path)
                existing_tests[rel] = {
                    "content": content,
                    "size": len(content),
                    "lines": content.count('\n') + 1,
                    "tested_source": tested_source,
                }
            except Exception:
                pass

    logger.info(f"Discovered {len(existing_tests)} existing test files")
    return existing_tests


def infer_source_file(test_path: str, language: str, repo_path: str) -> Optional[str]:
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
        if not is_test_file_strict(fp.name):
            found.append(str(fp.relative_to(root)))

    if len(found) == 1:
        return found[0]

    return None


def analyze_test_patterns(existing_tests: Dict[str, Dict[str, Any]], language: str) -> str:
    logger.info(f"Analyzing test patterns from {len(existing_tests)} existing tests")
    if not existing_tests:
        logger.info("No existing tests found to analyze")
        return ""

    sample_tests = []
    sorted_tests = sorted(existing_tests.items(), key=lambda x: x[1]["lines"], reverse=True)
    for test_path, test_info in sorted_tests[:2]:
        content = test_info["content"][:MAX_EXISTING_TEST_SAMPLE_SIZE]
        sample_tests.append(f"### File: {test_path}\n```{language}\n{content}\n```")

    samples_text = "\n\n".join(sample_tests)

    prompt = prompt_loader.get_prompt("unit_test_agent.yml", "test_pattern_analysis").format(
        language=language,
        samples_text=samples_text
    )

    try:
        logger.info("Calling AI service to analyze test patterns...")
        style_guide = ai_service.call_genai(prompt, temperature=0.1, max_tokens=2000)
        logger.info(f"Successfully generated style guide ({len(style_guide)} chars)")
        return style_guide.strip()
    except Exception as e:
        logger.error(f"Test pattern analysis error: {e}")
        print(f"⚠️ Test pattern analysis error: {e}")
        return ""


def build_coverage_map(
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


def identify_testable_modules(
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

    prompt = prompt_loader.get_prompt("unit_test_agent.yml", "test_gap_identification").format(
        language=language,
        file_list=file_list
    )

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
            return valid if valid else fallback_modules(source_files, coverage_map)
        return fallback_modules(source_files, coverage_map)
    except Exception as e:
        print(f"⚠️ Module identification error: {e}")
        return fallback_modules(source_files, coverage_map)


def fallback_modules(
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
