import uuid
import time
import threading
from typing import Dict, Any, Optional
from pathlib import Path

from .constants import logger, LANGUAGE_TEST_CONFIG, MAX_FIX_ATTEMPTS
from . import repo_analyzer
from . import test_discovery
from . import test_runner
from . import test_generator
from .test_runner import write_test_file, write_test_config


class UnitTestAgent:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, Dict[str, Any]] = {}
        logger.info("🧪 Unit Test Generator Agent initialized")
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
        logger.info(f"Setting repo for session {session_id}: {repo_name}")
        session = self._get_session(session_id)
        if session["cloned"]:
            logger.info(f"Repo already set for session {session_id}")
            return True

        if not Path(repo_path).exists():
            logger.error(f"Repo path does not exist: {repo_path}")
            return False

        logger.info(f"Detecting language for repo: {repo_path}")
        language = repo_analyzer.detect_language(repo_path)
        logger.info(f"Detected language: {language}")
        
        logger.info(f"Detecting tech stack for repo: {repo_path}")
        tech_stack = repo_analyzer.detect_tech_stack(repo_path, language)
        logger.info(f"Detected tech stack: {tech_stack}")
        
        session["repo_url"] = repo_url
        session["repo_path"] = repo_path
        session["repo_name"] = repo_name
        session["cloned"] = True
        session["language"] = language
        session["tech_stack"] = tech_stack
        print(f"🧪 Unit Test Agent linked to repo: {repo_name} at {repo_path}")
        print(f"📦 Detected tech stack: {tech_stack}")
        return True

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
            existing_tests = test_discovery.discover_existing_tests(repo_path, language)
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

                style_guide = test_discovery.analyze_test_patterns(existing_tests, language)
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

            source_files = repo_analyzer.collect_source_files(repo_path)
            task["thinking_steps"].append({"type": "tool_result", "content": f"Found {len(source_files)} source files"})
            task["progress"] = f"Found {len(source_files)} source files"

            if not source_files:
                task["status"] = "completed"
                task["success"] = False
                task["response"] = "No source files found in the repository to generate tests for."
                return

            deps_context = repo_analyzer.get_project_deps_context(repo_path, language)

            coverage_map = test_discovery.build_coverage_map(source_files, existing_tests)
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

            testable_modules = test_discovery.identify_testable_modules(source_files, language, coverage_map)
            task["thinking_steps"].append({"type": "tool_result", "content": f"Identified {len(testable_modules)} modules to process"})
            task["progress"] = f"Identified {len(testable_modules)} modules to process"

            write_test_config(repo_path, language)

            task["thinking_steps"].append({
                "type": "tool_call",
                "content": "Installing test dependencies",
                "tool_name": "install_deps"
            })
            task["progress"] = "Installing test dependencies..."
            deps_result = test_runner.install_test_deps(repo_path, language)
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

                imports_context = repo_analyzer.get_related_imports_context(filepath, content, source_files, language)

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

                test_result = test_generator.generate_tests_for_file(
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
                        test_path = test_generator.determine_test_path(filepath, language, repo_path, session.get("tech_stack"))

                    write_result = write_test_file(repo_path, test_path, test_result["test_code"])

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

                        run_result = test_runner.run_test_file(repo_path, test_path, language)

                        if run_result.get("passed"):
                            test_passed = True
                            task["thinking_steps"].append({
                                "type": "tool_result",
                                "content": f"✅ Tests PASSED on first run: {test_path}"
                            })
                        else:
                            error_output = run_result.get("output", "Unknown error")
                            logger.warning(f"Test failed for {test_path}")
                            logger.info(f"Captured error output: {len(error_output)} characters")
                            logger.info(f"Error preview: {error_output[:200]}...")
                            
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
                                    "error_message": error_output[:500],
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

                                logger.info(f"Sending to LLM for fix attempt {fix_attempts}/{MAX_FIX_ATTEMPTS}")
                                logger.info(f"Input: test_code={len(current_test_code)} chars, error_output={len(error_output)} chars")

                                fix_result = test_generator.fix_failing_tests(
                                    filepath, content, current_test_code,
                                    error_output, language, fix_attempts,
                                    deps_context=deps_context,
                                    repo_path=repo_path,
                                )

                                if fix_result["success"]:
                                    current_test_code = fix_result["test_code"]
                                    write_test_file(repo_path, test_path, current_test_code)

                                    rerun = test_runner.run_test_file(repo_path, test_path, language)
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

                            extract_result = test_generator.extract_passing_tests_only(
                                filepath, content, current_test_code,
                                error_output, language,
                            )

                            if extract_result["success"]:
                                cleaned_code = extract_result["test_code"]
                                write_test_file(repo_path, test_path, cleaned_code)
                                verify_run = test_runner.run_test_file(repo_path, test_path, language)
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
                        
                        if not test_passed and error_output:
                            entry["error_message"] = error_output[:500]

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
                    if not t.get("validated") and t.get("error_message"):
                        error_preview = t['error_message'].replace('\n', ' ')[:200]
                        response += f"| | **Error:** {error_preview}... | | |\n"
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
                    if not t.get("validated") and t.get("error_message"):
                        error_preview = t['error_message'].replace('\n', ' ')[:200]
                        response += f"| | **Error:** {error_preview}... | | |\n"
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
