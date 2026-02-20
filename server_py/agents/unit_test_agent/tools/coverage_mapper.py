import re
import json
import logging
from typing import Dict, Any, List

from ..ai_service import ai_service
from prompts import prompt_loader

logger = logging.getLogger(__name__)


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
