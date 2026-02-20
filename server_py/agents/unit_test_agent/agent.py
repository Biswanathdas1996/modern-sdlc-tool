import uuid
import time
import threading
from typing import Dict, Any, Optional
from pathlib import Path

from .constants import logger
from .tools.analyze_repo import detect_language, detect_tech_stack
from .tools.collect_sources import collect_source_files
from .tools.discover_tests import discover_existing_tests, analyze_test_patterns
from .tools.coverage_mapper import build_coverage_map, identify_testable_modules
from .tools.generate_tests import generate_tests_for_file
from .tools.run_tests import install_test_deps
from .tools.write_files import write_test_file, write_test_config
from .tools.validate_and_fix import validate_and_fix_test
from .tools.task_reporter import build_generation_report
from .helpers.deps_context import get_project_deps_context, get_related_imports_context
from .helpers.test_path import determine_test_path

MAX_FIX_ATTEMPTS = 2
TIME_BUDGET_SECONDS = 15 * 60


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

        language = detect_language(repo_path)
        tech_stack = detect_tech_stack(repo_path, language)
        logger.info(f"Detected language={language}, tech_stack={tech_stack}")

        session.update({
            "repo_url": repo_url,
            "repo_path": repo_path,
            "repo_name": repo_name,
            "cloned": True,
            "language": language,
            "tech_stack": tech_stack,
        })
        print(f"Unit Test Agent linked to repo: {repo_name} at {repo_path}")
        print(f" Detected tech stack: {tech_stack}")
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

        if intent == 'generate' or intent == 'general':
            return self._start_generate_task(session_id, session, thinking_steps)

        if intent == 'status':
            return self._build_status_response(session, thinking_steps)

        return {
            "success": True,
            "response": "I can help you with:\n- **Generate tests**: analyze the codebase and create unit tests\n- **Check status**: see what tests have been generated\n\nFor cloning repos and pushing code, use the **GitHub Agent**.\n\nWhat would you like to do?",
            "thinking_steps": thinking_steps,
        }

    def _start_generate_task(self, session_id: str, session: Dict, thinking_steps: list) -> Dict[str, Any]:
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
            args=(task_id, session_id, session["repo_path"], session["language"]),
            daemon=True,
        )
        thread.start()

        return {
            "success": True,
            "response": "Starting intelligent test generation with validation...\n\nHere's what I'll do:\n1. Scan for existing tests and learn your project's testing patterns\n2. Identify coverage gaps and generate new tests\n3. **Run each test file to verify it passes**\n4. **Auto-fix any failing tests** (up to 3 attempts per file)\n5. Only keep tests that are 100% passing\n\nThis may take several minutes since every test is validated by actually running it.",
            "thinking_steps": thinking_steps,
            "task_id": task_id,
        }

    def _build_status_response(self, session: Dict, thinking_steps: list) -> Dict[str, Any]:
        if session["tests_generated"]:
            response = f"**Tests generated so far:** {len(session['tests_generated'])}\n\n"
            for t in session["tests_generated"]:
                mode_label = "updated" if t.get("mode") == "augment" else "new"
                response += f"- `{t['test_path']}` ({mode_label}, from `{t['source_file']}`)\n"
            response += "\nSay **\"push to GitHub\"** to push these tests to a new branch."
        else:
            response = "No tests generated yet. Say **\"generate tests\"** to get started."
        return {"success": True, "response": response, "thinking_steps": thinking_steps}

    def _run_generate_task(self, task_id: str, session_id: str, repo_path: str, language: str):
        task = self.tasks[task_id]
        session = self._get_session(session_id)
        start_time = time.time()

        try:
            context = self._discover_and_prepare(task, session, repo_path, language)
            if context is None:
                return

            generated, augmented, failed = self._generate_all_modules(
                task, session, context, repo_path, language, start_time,
            )

            session["tests_generated"] = generated + augmented
            task["status"] = "completed"
            task["success"] = True
            task["response"] = build_generation_report(
                session, language, context["deps_installed"],
                context["deps_message"], context["existing_tests"],
                generated, augmented, failed,
            )
            task["progress"] = "Complete"

        except Exception as e:
            print(f"❌ Task {task_id} error: {e}")
            import traceback
            traceback.print_exc()
            task["status"] = "completed"
            task["success"] = False
            task["response"] = f"An error occurred during test generation: {str(e)}"
            task["progress"] = "Error"

    def _discover_and_prepare(self, task, session, repo_path, language):
        existing_tests = discover_existing_tests(repo_path, language)
        session["existing_tests"] = existing_tests
        task["thinking_steps"].append({
            "type": "tool_result",
            "content": f"Found {len(existing_tests)} existing test files" if existing_tests else "No existing tests found - will create from scratch"
        })
        task["progress"] = f"Found {len(existing_tests)} existing test files"

        style_guide = self._learn_test_patterns(task, session, existing_tests, language)

        task["thinking_steps"].append({"type": "tool_call", "content": "Collecting source files for analysis", "tool_name": "collect_sources"})
        task["progress"] = "Collecting source files..."
        source_files = collect_source_files(repo_path)
        task["thinking_steps"].append({"type": "tool_result", "content": f"Found {len(source_files)} source files"})

        if not source_files:
            task["status"] = "completed"
            task["success"] = False
            task["response"] = "No source files found in the repository to generate tests for."
            return None

        deps_context = get_project_deps_context(repo_path, language)

        coverage_map = build_coverage_map(source_files, existing_tests)
        covered = sum(1 for v in coverage_map.values() if v["has_existing_tests"])
        task["thinking_steps"].append({"type": "tool_result", "content": f"Coverage analysis: {covered} files with tests, {len(coverage_map) - covered} files without tests"})

        task["thinking_steps"].append({"type": "tool_call", "content": "Identifying testable modules and coverage gaps", "tool_name": "identify_modules"})
        task["progress"] = "Identifying coverage gaps..."
        testable_modules = identify_testable_modules(source_files, language, coverage_map)
        task["thinking_steps"].append({"type": "tool_result", "content": f"Identified {len(testable_modules)} modules to process"})

        write_test_config(repo_path, language)

        task["thinking_steps"].append({"type": "tool_call", "content": "Installing test dependencies", "tool_name": "install_deps"})
        task["progress"] = "Installing test dependencies..."
        deps_result = install_test_deps(repo_path, language)
        deps_installed = deps_result.get("success", False)
        task["thinking_steps"].append({"type": "tool_result", "content": f"Dependencies: {deps_result['message']}"})

        if not deps_installed:
            print(f"⚠️ Dependency installation failed for {repo_path}: {deps_result['message']}")
            task["thinking_steps"].append({"type": "tool_result", "content": f"⚠️ Dependency installation failed - tests will be generated but validation will be skipped\nReason: {deps_result['message']}"})

        return {
            "existing_tests": existing_tests,
            "style_guide": style_guide,
            "source_files": source_files,
            "coverage_map": coverage_map,
            "testable_modules": testable_modules,
            "deps_context": deps_context,
            "deps_installed": deps_installed,
            "deps_message": deps_result.get("message", ""),
        }

    def _learn_test_patterns(self, task, session, existing_tests, language):
        if not existing_tests:
            return ""
        task["thinking_steps"].append({
            "type": "tool_call",
            "content": f"Analyzing testing patterns from {min(2, len(existing_tests))} sample test files",
            "tool_name": "analyze_patterns"
        })
        task["progress"] = "Analyzing existing test patterns..."
        style_guide = analyze_test_patterns(existing_tests, language)
        session["test_style_guide"] = style_guide
        msg = "Extracted testing style guide from existing tests" if style_guide else "Could not extract patterns, will use framework defaults"
        task["thinking_steps"].append({"type": "tool_result", "content": msg})
        return style_guide

    def _generate_all_modules(self, task, session, context, repo_path, language, start_time):
        generated, augmented, failed = [], [], []
        modules = context["testable_modules"]

        for i, module in enumerate(modules):
            elapsed = time.time() - start_time
            if TIME_BUDGET_SECONDS - elapsed < 60:
                task["thinking_steps"].append({"type": "tool_result", "content": f"⏱️ Time budget reached ({int(elapsed)}s elapsed). Processed {i}/{len(modules)} modules."})
                break

            filepath = module["file"]
            if filepath not in context["source_files"]:
                continue

            result = self._process_single_module(
                task, session, context, module, filepath,
                repo_path, language, i + 1, len(modules), start_time,
            )

            if result is None:
                continue
            if result.get("failed"):
                failed.append(result["failed"])
            elif result.get("mode") == "augment":
                augmented.append(result["entry"])
            else:
                generated.append(result["entry"])

        return generated, augmented, failed

    def _process_single_module(self, task, session, context, module, filepath, repo_path, language, idx, total, start_time):
        mode = module.get("mode", "new")
        mode_label = "Augmenting" if mode == "augment" else "Generating"
        label = f"[{idx}/{total}]"

        task["thinking_steps"].append({"type": "tool_call", "content": f"{label} {mode_label} tests for: {filepath}", "tool_name": "generate_test"})
        task["progress"] = f"{mode_label} tests {label}: {filepath}"

        content = context["source_files"][filepath]
        imports_context = get_related_imports_context(filepath, content, context["source_files"], language)

        existing_test_content, augment_test_path = "", None
        if mode == "augment":
            test_files = context["coverage_map"].get(filepath, {}).get("existing_test_files", [])
            for tf in test_files:
                if tf in context["existing_tests"]:
                    existing_test_content = context["existing_tests"][tf]["content"]
                    augment_test_path = tf
                    break
            if not existing_test_content:
                mode = "new"

        test_result = generate_tests_for_file(
            filepath, content, language, repo_path,
            style_guide=context["style_guide"],
            existing_test_content=existing_test_content,
            mode=mode,
            deps_context=context["deps_context"],
            imports_context=imports_context,
            tech_stack=session.get("tech_stack"),
        )

        if not test_result["success"]:
            task["thinking_steps"].append({"type": "tool_result", "content": f"❌ Failed to generate tests for: {filepath}"})
            return {"failed": {"file": filepath, "error": test_result["error"]}}

        test_path = augment_test_path if (mode == "augment" and augment_test_path) else determine_test_path(filepath, language, repo_path, session.get("tech_stack"))
        write_result = write_test_file(repo_path, test_path, test_result["test_code"])

        if not write_result["success"]:
            task["thinking_steps"].append({"type": "tool_result", "content": f"❌ Failed to write: {test_path} - {write_result['error']}"})
            return {"failed": {"file": filepath, "error": write_result["error"]}}

        actual_mode = test_result.get("mode", mode)
        entry = {
            "source_file": filepath,
            "test_path": test_path,
            "priority": module.get("priority", "medium"),
            "mode": actual_mode,
        }

        if not context["deps_installed"]:
            entry.update({"validated": False, "fix_attempts": 0})
            action = "Updated" if actual_mode == "augment" else "Created"
            task["thinking_steps"].append({"type": "tool_result", "content": f"✅ {action}: {test_path} (validation skipped - deps not installed)"})
            return {"entry": entry, "mode": actual_mode}

        remaining = TIME_BUDGET_SECONDS - (time.time() - start_time)
        vr = validate_and_fix_test(
            repo_path, test_path, test_result["test_code"],
            filepath, content, language, context["deps_context"],
            MAX_FIX_ATTEMPTS, remaining, task, idx, total,
        )

        entry.update({"validated": vr["passed"], "fix_attempts": vr["fix_attempts"]})
        if not vr["passed"] and vr["error_output"]:
            entry["error_message"] = vr["error_output"][:500]

        if not vr["passed"]:
            task["thinking_steps"].append({"type": "tool_result", "content": f"⚠️ Kept {test_path} (not all tests passing after {vr['fix_attempts']} fix attempts - file preserved for manual review)"})

        return {"entry": entry, "mode": actual_mode}

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
