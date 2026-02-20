from typing import Dict, Any, List

from ..constants import LANGUAGE_TEST_CONFIG


def build_generation_report(
    session: Dict[str, Any],
    language: str,
    deps_installed: bool,
    deps_message: str,
    existing_tests: Dict,
    generated_tests: List[Dict],
    augmented_tests: List[Dict],
    failed_tests: List[Dict],
) -> str:
    config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])
    all_tests = generated_tests + augmented_tests
    validated_count = sum(1 for t in all_tests if t.get("validated"))
    unvalidated_count = sum(1 for t in all_tests if not t.get("validated"))
    total_count = len(all_tests)

    response = "## Unit Test Generation Complete\n\n"
    response += f"**Repository:** {session['repo_name']}\n"
    response += f"**Language:** {language.title()} | **Framework:** {config['framework']}\n"

    if unvalidated_count == 0 and validated_count > 0:
        response += f"**All {validated_count} test files validated - 100% passing** ✅\n\n"
    elif validated_count > 0:
        response += f"**{validated_count}/{total_count} test files validated and passing** ✅\n\n"
    else:
        response += f"**{total_count} test files generated**\n\n"
        if not deps_installed and "npm not found" in deps_message:
            response += "⚠️ **Tests not validated** - npm not installed. Install Node.js from https://nodejs.org/ then regenerate tests.\n\n"

    if existing_tests:
        response += f"**Existing tests found:** {len(existing_tests)} files (patterns analyzed and followed)\n\n"

    if generated_tests:
        response += _build_test_table("✅ New Test Files Created", generated_tests)

    if augmented_tests:
        response += _build_test_table("🔄 Existing Tests Updated", augmented_tests)

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

    return response


def _build_test_table(heading: str, tests: List[Dict]) -> str:
    result = f"### {heading}: {len(tests)}\n\n"
    result += "| Source File | Test File | Priority | Status |\n"
    result += "|---|---|---|---|\n"
    for t in tests:
        status = _format_test_status(t)
        result += f"| `{t['source_file']}` | `{t['test_path']}` | {t['priority']} | {status} |\n"
        if not t.get("validated") and t.get("error_message"):
            error_preview = t['error_message'].replace('\n', ' ')[:200]
            result += f"| | **Error:** {error_preview}... | | |\n"
    result += "\n"
    return result


def _format_test_status(t: Dict) -> str:
    if t.get("validated"):
        fix_note = ""
        if t.get('fix_attempts', 0) > 0:
            n = t['fix_attempts']
            fix_note = f" (fixed in {n} attempt{'s' if n != 1 else ''})"
        return f"✅ Passing{fix_note}"
    if t.get("fix_attempts", 0) > 0:
        return f"⚠️ Needs review (kept after {t['fix_attempts']} fix attempts)"
    return "⚠️ Not validated"
