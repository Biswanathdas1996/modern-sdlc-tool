import time
from typing import Dict, Any

from ..constants import logger
from .fix_tests import fix_failing_tests, extract_passing_tests_only
from .run_tests import run_test_file
from .write_files import write_test_file


def validate_and_fix_test(
    repo_path: str,
    test_path: str,
    test_code: str,
    source_filepath: str,
    source_content: str,
    language: str,
    deps_context: str,
    max_fix_attempts: int,
    time_budget_remaining: float,
    task: Dict[str, Any],
    module_index: int,
    total_modules: int,
) -> Dict[str, Any]:
    label = f"[{module_index}/{total_modules}]"

    task["thinking_steps"].append({
        "type": "tool_call",
        "content": f"Running tests to validate: {test_path}",
        "tool_name": "run_test"
    })
    task["progress"] = f"Validating tests {label}: {test_path}"

    current_test_code = test_code
    test_passed = False
    fix_attempts = 0
    error_output = ""

    run_result = run_test_file(repo_path, test_path, language)

    if run_result.get("passed"):
        test_passed = True
        task["thinking_steps"].append({
            "type": "tool_result",
            "content": f"✅ Tests PASSED on first run: {test_path}"
        })
        return _result(True, 0, current_test_code, "")

    error_output = run_result.get("output", "Unknown error")
    logger.warning(f"Test failed for {test_path}")
    logger.info(f"Captured error output: {len(error_output)} characters")
    logger.info(f"Error preview: {error_output[:200]}...")

    if time_budget_remaining < 90:
        task["thinking_steps"].append({
            "type": "tool_result",
            "content": f"⚠️ Tests failed but time budget low - skipping fix attempts for {test_path}"
        })
        return _result(False, 0, current_test_code, error_output)

    task["thinking_steps"].append({
        "type": "tool_result",
        "content": f"⚠️ Tests failed, attempting AI-powered fix (attempt 1/{max_fix_attempts})"
    })

    current_test_code, test_passed, fix_attempts, error_output = _run_fix_loop(
        repo_path, test_path, source_filepath, source_content,
        current_test_code, error_output, language, deps_context,
        max_fix_attempts, task, module_index, total_modules,
    )

    if not test_passed and fix_attempts >= max_fix_attempts:
        current_test_code, test_passed, error_output = _try_extract_passing(
            repo_path, test_path, source_filepath, source_content,
            current_test_code, error_output, language, task, module_index, total_modules,
        )

    return _result(test_passed, fix_attempts, current_test_code, error_output)


def _run_fix_loop(
    repo_path, test_path, source_filepath, source_content,
    current_test_code, error_output, language, deps_context,
    max_fix_attempts, task, module_index, total_modules,
):
    test_passed = False
    fix_attempts = 0
    label = f"[{module_index}/{total_modules}]"

    while not test_passed and fix_attempts < max_fix_attempts:
        fix_attempts += 1
        task["progress"] = f"Fixing tests {label} (attempt {fix_attempts}/{max_fix_attempts}): {source_filepath}"

        task["thinking_steps"].append({
            "type": "tool_call",
            "content": f"AI fixing test failures (attempt {fix_attempts}/{max_fix_attempts})",
            "tool_name": "fix_test"
        })

        logger.info(f"Sending to LLM for fix attempt {fix_attempts}/{max_fix_attempts}")
        logger.info(f"Input: test_code={len(current_test_code)} chars, error_output={len(error_output)} chars")

        fix_result = fix_failing_tests(
            source_filepath, source_content, current_test_code,
            error_output, language, fix_attempts,
            deps_context=deps_context,
            repo_path=repo_path,
        )

        if not fix_result["success"]:
            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"⚠️ AI fix failed: {fix_result.get('error', 'unknown')}"
            })
            break

        current_test_code = fix_result["test_code"]
        write_test_file(repo_path, test_path, current_test_code)

        rerun = run_test_file(repo_path, test_path, language)
        if rerun.get("passed"):
            test_passed = True
            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"✅ Tests PASSED after fix attempt {fix_attempts}"
            })
        else:
            error_output = rerun.get("output", "Unknown error")
            logger.warning(f"Tests still failing after fix attempt {fix_attempts}")
            logger.info(f"Updated error output: {len(error_output)} characters")
            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"⚠️ Tests still failing after attempt {fix_attempts}"
            })

    return current_test_code, test_passed, fix_attempts, error_output


def _try_extract_passing(
    repo_path, test_path, source_filepath, source_content,
    current_test_code, error_output, language, task, module_index, total_modules,
):
    label = f"[{module_index}/{total_modules}]"

    task["thinking_steps"].append({
        "type": "tool_call",
        "content": f"Extracting only passing tests from {test_path}",
        "tool_name": "extract_passing"
    })
    task["progress"] = f"Extracting passing tests {label}: {source_filepath}"

    extract_result = extract_passing_tests_only(
        source_filepath, source_content, current_test_code,
        error_output, language,
    )

    if not extract_result["success"]:
        return current_test_code, False, error_output

    cleaned_code = extract_result["test_code"]
    write_test_file(repo_path, test_path, cleaned_code)
    verify_run = run_test_file(repo_path, test_path, language)

    if verify_run.get("passed"):
        task["thinking_steps"].append({
            "type": "tool_result",
            "content": f"✅ Kept only passing tests in {test_path} (removed failing ones)"
        })
        return cleaned_code, True, ""

    task["thinking_steps"].append({
        "type": "tool_result",
        "content": "⚠️ Extracted tests still failing - will remove file"
    })
    return current_test_code, False, error_output


def _result(passed: bool, fix_attempts: int, test_code: str, error_output: str) -> Dict[str, Any]:
    return {
        "passed": passed,
        "fix_attempts": fix_attempts,
        "test_code": test_code,
        "error_output": error_output,
    }
