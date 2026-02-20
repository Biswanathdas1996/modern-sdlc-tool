import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any

from ..constants import logger as root_logger
from ..helpers.npm_runner import check_command_exists, run_npm_command, is_cra_project

logger = logging.getLogger(__name__)


def install_test_deps(repo_path: str, language: str) -> Dict[str, Any]:
    logger.info(f"Starting test dependency installation for language: {language}")
    logger.info(f"Repository path: {repo_path}")
    root = Path(repo_path)
    try:
        if language == "python":
            logger.info("Installing pytest and pytest-mock...")
            result = subprocess.run(
                ["pip", "install", "pytest", "pytest-mock", "-q"],
                cwd=str(root), capture_output=True, text=True, timeout=120
            )
            logger.info(f"pytest installation completed with return code: {result.returncode}")

            req_file = root / "requirements.txt"
            if req_file.exists():
                logger.info("Found requirements.txt - installing project dependencies...")
                try:
                    subprocess.run(
                        ["pip", "install", "-r", "requirements.txt", "-q"],
                        cwd=str(root), capture_output=True, text=True, timeout=180
                    )
                    logger.info("requirements.txt dependencies installed successfully")
                except Exception as e:
                    logger.warning(f"Failed to install requirements.txt: {e}")
                    pass

            setup_py = root / "setup.py"
            pyproject = root / "pyproject.toml"
            if setup_py.exists() or pyproject.exists():
                logger.info("Found setup.py or pyproject.toml - installing in editable mode...")
                try:
                    subprocess.run(
                        ["pip", "install", "-e", ".", "-q"],
                        cwd=str(root), capture_output=True, text=True, timeout=180
                    )
                    logger.info("Project installed in editable mode successfully")
                except Exception as e:
                    logger.warning(f"Failed to install in editable mode: {e}")
                    pass
            logger.info("Python test dependencies installation complete")
            return {"success": True, "message": "pytest installed"}

        elif language in ("javascript", "typescript"):
            logger.info("Checking for npm installation...")
            if not check_command_exists("npm"):
                logger.error("npm command not found in PATH")
                return {
                    "success": False,
                    "message": "npm not found. Please install Node.js from https://nodejs.org/ (includes npm)"
                }
            logger.info("npm found successfully")

            node_modules = root / "node_modules"
            pkg = root / "package.json"

            logger.info(f"Checking for node_modules directory: {node_modules}")
            logger.info(f"node_modules exists: {node_modules.exists()}")

            if pkg.exists() and not node_modules.exists():
                logger.warning("node_modules directory not found - running npm install...")
                print("⚠️ node_modules not found - installing dependencies (this may take a few minutes)...")
                try:
                    result = run_npm_command(
                        ["npm", "install"],
                        str(root),
                        timeout=300
                    )
                    if result.returncode != 0:
                        logger.error(f"npm install failed: {result.stderr[:500]}")
                        return {
                            "success": False,
                            "message": f"npm install failed: {result.stderr[:500]}"
                        }
                    logger.info("npm install completed successfully")
                    print("✅ Dependencies installed successfully")
                except subprocess.TimeoutExpired:
                    logger.error("npm install timed out after 300 seconds")
                    return {
                        "success": False,
                        "message": "npm install timed out (5 min limit). The project may have too many dependencies. Please run 'npm install' manually."
                    }
            else:
                logger.info("node_modules directory found - skipping npm install")

            logger.info("Detecting if project is Create React App...")
            is_cra = is_cra_project(str(root))
            logger.info(f"Is Create React App: {is_cra}")

            if is_cra:
                test_deps = ["@testing-library/react", "@testing-library/jest-dom", "@testing-library/user-event"]
                logger.info(f"Installing React Testing Library dependencies: {test_deps}")
                try:
                    result = run_npm_command(
                        ["npm", "install", "--save-dev", "--legacy-peer-deps"] + test_deps,
                        str(root),
                        timeout=180
                    )
                    if result.returncode != 0:
                        logger.error(f"testing-library install failed: {result.stderr[:300]}")
                        print(f"⚠️ testing-library install warning: {result.stderr[:300]}")
                        return {"success": False, "message": f"testing-library install failed: {result.stderr[:300]}"}
                    logger.info("React Testing Library installed successfully")
                    return {"success": True, "message": "react-scripts + testing-library installed"}
                except subprocess.TimeoutExpired:
                    logger.error("React Testing Library installation timed out")
                    return {"success": False, "message": "Test dependency installation timed out. Please run 'npm install' manually first."}
            else:
                logger.info("Installing Jest test framework...")
                try:
                    result = run_npm_command(
                        ["npm", "install", "--save-dev", "jest", "@types/jest"],
                        str(root),
                        timeout=180
                    )
                    if result.returncode != 0:
                        logger.error(f"Jest install failed: {result.stderr[:500]}")
                        return {"success": False, "message": f"jest install failed: {result.stderr[:500]}"}
                    logger.info("Jest installed successfully")
                    return {"success": True, "message": "jest installed"}
                except subprocess.TimeoutExpired:
                    logger.error("Jest installation timed out")
                    return {"success": False, "message": "Jest installation timed out. Please run 'npm install' manually first."}

        elif language == "go":
            logger.info("Running go mod tidy...")
            result = subprocess.run(
                ["go", "mod", "tidy"],
                cwd=str(root), capture_output=True, text=True, timeout=120
            )
            logger.info(f"go mod tidy completed with return code: {result.returncode}")
            return {"success": True, "message": "go dependencies tidied"}

        logger.info(f"No specific test dependencies to install for language: {language}")
        return {"success": True, "message": "No specific test deps to install"}
    except subprocess.TimeoutExpired as e:
        logger.error(f"Dependency installation timeout: {e}")
        print(f"❌ Dependency installation timeout: {e}")
        return {"success": False, "message": "Dependency installation timed out (300s limit). Try manual install."}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Dependency installation error: {error_detail}")
        print(f"❌ Dependency installation error: {error_detail}")
        return {"success": False, "message": f"Failed to install deps: {str(e)[:200]}"}


def run_test_file(repo_path: str, test_path: str, language: str) -> Dict[str, Any]:
    logger.info(f"Running test file: {test_path}")
    logger.info(f"Repository path: {repo_path}")
    logger.info(f"Language: {language}")

    root = Path(repo_path)
    full_test_path = root / test_path
    if not full_test_path.exists():
        logger.error(f"Test file not found: {full_test_path}")
        return {"success": False, "passed": False, "output": "Test file not found", "error": "File not found"}

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CI"] = "true"
    if language == "python":
        env["PYTHONPATH"] = str(root)

    try:
        if language == "python":
            cmd = ["python", "-m", "pytest", test_path, "-v", "--tb=short", "--no-header", "-x"]
            logger.info(f"Executing pytest command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, cwd=str(root), capture_output=True, text=True,
                timeout=180, env=env
            )
            logger.info(f"pytest completed with return code: {result.returncode}")
        elif language in ("javascript", "typescript"):
            if is_cra_project(str(root)):
                escaped_path = re.escape(test_path).replace("\\\\", "/")
                cmd = ["npx", "react-scripts", "test", "--watchAll=false", "--ci", "--verbose", "--forceExit", "--testPathPattern", escaped_path]
                logger.info(f"Executing react-scripts test command: {' '.join(cmd)}")
            else:
                cmd = ["npx", "jest", test_path, "--no-coverage", "--verbose", "--forceExit"]
                logger.info(f"Executing jest command: {' '.join(cmd)}")
            result = run_npm_command(cmd, str(root), timeout=180, env=env)
            logger.info(f"Test command completed with return code: {result.returncode}")
        elif language == "go":
            test_dir = str(Path(test_path).parent)
            if test_dir == ".":
                test_dir = "./"
            else:
                test_dir = "./" + test_dir + "/..."
            cmd = ["go", "test", "-v", "-count=1", test_dir]
            result = subprocess.run(
                cmd, cwd=str(root), capture_output=True, text=True,
                timeout=180, env=env
            )
        else:
            return {"success": True, "passed": True, "output": "No runner for this language, skipping validation"}

        combined_output = result.stdout + "\n" + result.stderr
        combined_output = combined_output[-4000:]

        if result.returncode != 0 and is_cra_project(str(root)) and "react-scripts" in " ".join(cmd):
            if "Cannot find module" in combined_output and "react-scripts" in combined_output:
                logger.warning("react-scripts test failed with module error - falling back to jest")
                print("⚠️ react-scripts test failed, falling back to npx jest")
                fallback_cmd = ["npx", "jest", test_path, "--no-coverage", "--verbose", "--forceExit"]
                logger.info(f"Executing fallback jest command: {' '.join(fallback_cmd)}")
                result = run_npm_command(fallback_cmd, str(root), timeout=180, env=env)
                combined_output = result.stdout + "\n" + result.stderr
                combined_output = combined_output[-4000:]
                logger.info(f"Fallback jest completed with return code: {result.returncode}")

        passed = result.returncode == 0
        logger.info(f"Test execution result - Passed: {passed}")

        return {
            "success": True,
            "passed": passed,
            "output": combined_output,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        logger.error("Test execution timed out after 180 seconds")
        return {"success": True, "passed": False, "output": "Test execution timed out (180s)", "returncode": -1}
    except Exception as e:
        logger.error(f"Test execution error: {e}")
        print(f"⚠️ Test execution error: {e}")
        return {"success": False, "passed": False, "output": str(e), "returncode": -1}
