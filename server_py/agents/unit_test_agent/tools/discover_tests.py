import logging
from pathlib import Path
from typing import Dict, Any

from ..ai_service import ai_service
from prompts import prompt_loader
from ..constants import (
    IGNORE_DIRS, SOURCE_EXTENSIONS,
    MAX_FILE_SIZE, MAX_EXISTING_TEST_SAMPLE_SIZE,
)
from ..utils.pattern_matcher import is_test_file_by_context, infer_source_file

logger = logging.getLogger(__name__)


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
