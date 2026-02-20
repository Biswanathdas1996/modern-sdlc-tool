import os
import json
import time
import uuid
import subprocess
import threading
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from utils.pwc_llm import call_pwc_genai_async, build_pwc_prompt
from utils.text import parse_json_response
from prompts import prompt_loader


class CodeGenAgent:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, Dict[str, Any]] = {}
        print("🔧 Code Generation Agent initialized")

    def _get_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "repo_url": None,
                "repo_path": None,
                "repo_name": None,
                "cloned": False,
                "language": None,
                "generated_changes": [],
            }
        return self.sessions[session_id]

    def set_repo(self, session_id: str, repo_url: str, repo_path: str, repo_name: str):
        session = self._get_session(session_id)
        if not Path(repo_path).exists():
            return False
        session["repo_url"] = repo_url
        session["repo_path"] = repo_path
        session["repo_name"] = repo_name
        session["cloned"] = True
        session["language"] = self._detect_language(repo_path)
        print(f"🔧 Code Gen Agent linked to repo: {repo_name} at {repo_path}")
        return True

    def _detect_language(self, repo_path: str) -> str:
        root = Path(repo_path)
        ext_counts: Dict[str, int] = {}
        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", "vendor"}
        for f in root.rglob("*"):
            if any(part in skip_dirs for part in f.parts):
                continue
            if f.is_file():
                ext = f.suffix.lower()
                if ext in (".ts", ".tsx"):
                    ext_counts["typescript"] = ext_counts.get("typescript", 0) + 1
                elif ext in (".js", ".jsx"):
                    ext_counts["javascript"] = ext_counts.get("javascript", 0) + 1
                elif ext == ".py":
                    ext_counts["python"] = ext_counts.get("python", 0) + 1
                elif ext == ".go":
                    ext_counts["go"] = ext_counts.get("go", 0) + 1
                elif ext in (".java",):
                    ext_counts["java"] = ext_counts.get("java", 0) + 1
        if not ext_counts:
            return "javascript"
        return max(ext_counts, key=ext_counts.get)

    def _get_file_tree(self, repo_path: str, max_depth: int = 4) -> str:
        root = Path(repo_path)
        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".next", "vendor", "coverage", ".cache"}
        lines = []

        def walk(path: Path, depth: int, prefix: str = ""):
            if depth > max_depth:
                return
            try:
                entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return
            dirs = [e for e in entries if e.is_dir() and e.name not in skip_dirs]
            files = [e for e in entries if e.is_file()]
            for f in files[:30]:
                lines.append(f"{prefix}{f.name}")
            if len(files) > 30:
                lines.append(f"{prefix}... ({len(files) - 30} more files)")
            for d in dirs[:15]:
                lines.append(f"{prefix}{d.name}/")
                walk(d, depth + 1, prefix + "  ")

        walk(root, 0)
        return "\n".join(lines[:200])

    def _read_file_safe(self, filepath: str, max_chars: int = 8000) -> str:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(max_chars)
            return content
        except Exception:
            return ""

    def _collect_key_files(self, repo_path: str) -> Dict[str, str]:
        root = Path(repo_path)
        key_files = {}
        config_names = [
            "package.json", "tsconfig.json", "requirements.txt", "setup.py", "pyproject.toml",
            "go.mod", "Cargo.toml", "pom.xml", "build.gradle", ".eslintrc.json", ".prettierrc",
            "Makefile", "docker-compose.yml", "Dockerfile",
        ]
        for name in config_names:
            fp = root / name
            if fp.exists():
                key_files[name] = self._read_file_safe(str(fp), 4000)

        readme = root / "README.md"
        if readme.exists():
            key_files["README.md"] = self._read_file_safe(str(readme), 3000)

        return key_files

    def _collect_source_files(self, repo_path: str) -> Dict[str, str]:
        root = Path(repo_path)
        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".next", "vendor", "coverage", ".cache", "test", "tests", "__tests__"}
        source_exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".cs", ".rb", ".rs"}
        sources = {}
        for f in sorted(root.rglob("*")):
            if any(part in skip_dirs for part in f.parts):
                continue
            if f.is_file() and f.suffix.lower() in source_exts:
                rel = str(f.relative_to(root))
                if "test" in rel.lower() or "spec" in rel.lower():
                    continue
                sources[rel] = self._read_file_safe(str(f), 6000)
                if len(sources) >= 40:
                    break
        return sources

    def start_generation(self, session_id: str, user_stories: List[Dict], copilot_prompt: str,
                         documentation: Optional[Dict] = None, analysis: Optional[Dict] = None,
                         database_schema: Optional[Dict] = None) -> Dict[str, Any]:
        session = self._get_session(session_id)
        if not session.get("cloned") or not session.get("repo_path"):
            return {"success": False, "error": "No repository cloned. Please analyze a repository first."}

        repo_path = session["repo_path"]
        if not os.path.exists(repo_path):
            return {"success": False, "error": "Cloned repository no longer exists."}

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "status": "running",
            "thinking_steps": [
                {"type": "tool_call", "content": "Analyzing repository architecture", "tool_name": "analyze_repo"}
            ],
            "progress": "Analyzing repository...",
            "response": None,
            "success": None,
            "task_id": task_id,
            "session_id": session_id,
        }

        thread = threading.Thread(
            target=self._run_generation_task,
            args=(task_id, session_id, repo_path, user_stories, copilot_prompt, documentation, analysis, database_schema),
            daemon=True
        )
        thread.start()

        return {"success": True, "task_id": task_id}

    def _run_generation_task(self, task_id: str, session_id: str, repo_path: str,
                              user_stories: List[Dict], copilot_prompt: str,
                              documentation: Optional[Dict], analysis: Optional[Dict],
                              database_schema: Optional[Dict]):
        task = self.tasks[task_id]
        session = self._get_session(session_id)
        start_time = time.time()

        try:
            file_tree = self._get_file_tree(repo_path)
            key_files = self._collect_key_files(repo_path)
            source_files = self._collect_source_files(repo_path)
            language = session.get("language", "javascript")

            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"Repository analyzed: {len(source_files)} source files, language: {language}"
            })
            task["progress"] = "Creating implementation plan..."

            key_files_text = ""
            for name, content in key_files.items():
                key_files_text += f"\n--- {name} ---\n{content[:2000]}\n"

            arch_context = ""
            if documentation:
                arch_context += f"\nDocumentation Title: {documentation.get('title', '')}\n"
                content = documentation.get('content', '')
                if content:
                    arch_context += f"Documentation:\n{content[:3000]}\n"
            if analysis:
                tech_stack = analysis.get('techStack', {})
                if tech_stack:
                    arch_context += f"\nTech Stack: {json.dumps(tech_stack, indent=2)}\n"
            if database_schema:
                tables = database_schema.get('tables', [])
                if tables:
                    arch_context += f"\nDatabase Schema ({len(tables)} tables):\n"
                    for t in tables[:10]:
                        cols = ", ".join([c.get("name", "") for c in t.get("columns", [])[:8]])
                        arch_context += f"  - {t.get('tableName', '')}: {cols}\n"

            source_samples = ""
            sample_files = list(source_files.items())[:15]
            for filepath, content in sample_files:
                source_samples += f"\n--- {filepath} ---\n{content[:3000]}\n"

            stories_text = ""
            for i, story in enumerate(user_stories):
                stories_text += f"\n### Story {i+1}: {story.get('title', story.get('storyKey', ''))}\n"
                stories_text += f"Description: {story.get('description', '')}\n"
                ac = story.get('acceptanceCriteria', [])
                if ac:
                    stories_text += "Acceptance Criteria:\n"
                    for c in ac:
                        stories_text += f"  - {c}\n"

            task["thinking_steps"].append({
                "type": "tool_call",
                "content": "Creating implementation plan with AI",
                "tool_name": "plan_implementation"
            })

            plan_prompt = build_pwc_prompt(
                prompt_loader.get_prompt("code_gen_agent.yml", "plan_implementation_system"),
                prompt_loader.get_prompt("code_gen_agent.yml", "plan_implementation_user").format(
                    file_tree=file_tree,
                    key_files_text=key_files_text,
                    arch_context=arch_context,
                    source_samples=source_samples,
                    stories_text=stories_text,
                    copilot_prompt=copilot_prompt[:3000]
                )
            )

            import asyncio
            loop = asyncio.new_event_loop()
            plan_text = loop.run_until_complete(call_pwc_genai_async(plan_prompt, task_name="code_gen_plan"))

            try:
                change_plan = parse_json_response(plan_text)
                if not isinstance(change_plan, list):
                    change_plan = [change_plan] if isinstance(change_plan, dict) else []
            except Exception:
                change_plan = []
                lines = plan_text.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            item = json.loads(line)
                            change_plan.append(item)
                        except:
                            pass

            if not change_plan:
                task["status"] = "completed"
                task["success"] = False
                task["response"] = "Could not create an implementation plan. The AI was unable to parse the repository structure. Please try again."
                task["progress"] = "Error"
                return

            task["thinking_steps"].append({
                "type": "tool_result",
                "content": f"Implementation plan created: {len(change_plan)} file changes"
            })

            generated_changes = []
            total_files = len(change_plan)

            for idx, change in enumerate(change_plan):
                file_path = change.get("file_path", "")
                action = change.get("action", "create")
                description = change.get("description", "")
                story_refs = change.get("story_refs", [])

                if not file_path:
                    continue

                task["progress"] = f"Generating code [{idx+1}/{total_files}]: {file_path}"
                task["thinking_steps"].append({
                    "type": "tool_call",
                    "content": f"Generating code for: {file_path} ({action})",
                    "tool_name": "generate_code"
                })

                existing_content = ""
                full_path = os.path.join(repo_path, file_path)
                if action == "modify" and os.path.exists(full_path):
                    existing_content = self._read_file_safe(full_path, 10000)

                related_files_content = ""
                file_dir = os.path.dirname(file_path)
                if file_dir:
                    dir_path = Path(repo_path) / file_dir
                    if dir_path.exists():
                        siblings = []
                        for f in sorted(dir_path.iterdir()):
                            if f.is_file() and f.name != os.path.basename(file_path):
                                siblings.append(f)
                        for sib in siblings[:3]:
                            rel = str(sib.relative_to(Path(repo_path)))
                            sib_content = self._read_file_safe(str(sib), 3000)
                            if sib_content:
                                related_files_content += f"\n--- {rel} ---\n{sib_content}\n"

                if action == "modify":
                    code_prompt = build_pwc_prompt(
                        prompt_loader.get_prompt("code_gen_agent.yml", "modify_file_system").format(language=language),
                        prompt_loader.get_prompt("code_gen_agent.yml", "modify_file_user").format(
                            file_path=file_path,
                            existing_content=existing_content,
                            related_files_content=related_files_content,
                            description=description,
                            stories_text=stories_text,
                            arch_context=arch_context
                        )
                    )
                else:
                    code_prompt = build_pwc_prompt(
                        prompt_loader.get_prompt("code_gen_agent.yml", "create_file_system").format(language=language),
                        prompt_loader.get_prompt("code_gen_agent.yml", "create_file_user").format(
                            file_path=file_path,
                            related_files_content=related_files_content,
                            key_files_text=key_files_text[:2000],
                            description=description,
                            stories_text=stories_text,
                            arch_context=arch_context
                        )
                    )

                try:
                    generated_code = loop.run_until_complete(call_pwc_genai_async(code_prompt, task_name="code_gen_implementation"))

                    generated_code = generated_code.strip()
                    if generated_code.startswith("```"):
                        first_nl = generated_code.index("\n")
                        generated_code = generated_code[first_nl + 1:]
                    if generated_code.endswith("```"):
                        generated_code = generated_code[:-3].rstrip()

                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(generated_code)

                    generated_changes.append({
                        "file_path": file_path,
                        "action": action,
                        "description": description,
                        "story_refs": story_refs,
                        "success": True,
                        "lines": len(generated_code.split("\n")),
                    })

                    task["thinking_steps"].append({
                        "type": "tool_result",
                        "content": f"✅ {action.title()}d: {file_path} ({len(generated_code.split(chr(10)))} lines)"
                    })
                except Exception as e:
                    generated_changes.append({
                        "file_path": file_path,
                        "action": action,
                        "description": description,
                        "story_refs": story_refs,
                        "success": False,
                        "error": str(e),
                    })
                    task["thinking_steps"].append({
                        "type": "tool_result",
                        "content": f"❌ Failed: {file_path} - {str(e)}"
                    })

            loop.close()

            session["generated_changes"] = generated_changes

            elapsed = time.time() - start_time
            success_count = sum(1 for c in generated_changes if c.get("success"))
            fail_count = sum(1 for c in generated_changes if not c.get("success"))

            response = f"## Code Generation Complete\n\n"
            response += f"**Repository:** {session.get('repo_name', 'Unknown')}\n"
            response += f"**Language:** {language.title()}\n"
            response += f"**Time:** {elapsed:.0f}s\n\n"

            if success_count > 0:
                created = [c for c in generated_changes if c.get("success") and c["action"] == "create"]
                modified = [c for c in generated_changes if c.get("success") and c["action"] == "modify"]

                if created:
                    response += f"### New Files Created: {len(created)}\n\n"
                    response += "| File | Description | Stories |\n"
                    response += "|---|---|---|\n"
                    for c in created:
                        refs = ", ".join(c.get("story_refs", []))
                        response += f"| `{c['file_path']}` | {c['description'][:80]} | {refs} |\n"
                    response += "\n"

                if modified:
                    response += f"### Files Modified: {len(modified)}\n\n"
                    response += "| File | Description | Stories |\n"
                    response += "|---|---|---|\n"
                    for c in modified:
                        refs = ", ".join(c.get("story_refs", []))
                        response += f"| `{c['file_path']}` | {c['description'][:80]} | {refs} |\n"
                    response += "\n"

            if fail_count > 0:
                response += f"### Failed: {fail_count} files\n\n"
                for c in generated_changes:
                    if not c.get("success"):
                        response += f"- `{c['file_path']}`: {c.get('error', 'Unknown error')}\n"
                response += "\n"

            response += "---\n\n"
            response += "**Push to GitHub** to create a new branch with these changes and open a pull request."

            task["status"] = "completed"
            task["success"] = True
            task["response"] = response
            task["progress"] = "Complete"
            task["elapsed"] = round(elapsed)

        except Exception as e:
            print(f"❌ Code gen task {task_id} error: {e}")
            import traceback
            traceback.print_exc()
            task["status"] = "completed"
            task["success"] = False
            task["response"] = f"An error occurred during code generation: {str(e)}"
            task["progress"] = "Error"

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.tasks.get(task_id)
        if not task:
            return None
        result = {
            "task_id": task_id,
            "status": task["status"],
            "progress": task.get("progress", ""),
            "thinking_steps": task.get("thinking_steps", []),
            "response": task.get("response"),
            "success": task.get("success"),
        }
        if task["status"] == "completed" and task.get("session_id"):
            session = self.sessions.get(task["session_id"], {})
            result["generated_changes"] = session.get("generated_changes", [])
            result["meta"] = {
                "repo_name": session.get("repo_name", ""),
                "language": session.get("language", ""),
                "elapsed": task.get("elapsed", 0),
            }
        return result


code_gen_agent = CodeGenAgent()
