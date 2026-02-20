import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def write_test_file(repo_path: str, test_path: str, test_code: str) -> Dict[str, Any]:
    logger.info(f"Writing test file: {test_path}")
    try:
        full_path = Path(repo_path) / test_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(test_code, encoding='utf-8')
        logger.info(f"Successfully wrote test file: {test_path} ({len(test_code)} chars)")
        return {"success": True, "path": test_path}
    except Exception as e:
        logger.error(f"Failed to write test file {test_path}: {e}")
        return {"success": False, "error": str(e), "path": test_path}


def write_test_config(repo_path: str, language: str):
    root = Path(repo_path)
    if language == "python":
        conftest = root / "tests" / "conftest.py"
        if not conftest.exists():
            conftest.parent.mkdir(parents=True, exist_ok=True)
            conftest.write_text("", encoding='utf-8')
        init = root / "tests" / "__init__.py"
        if not init.exists():
            init.write_text("", encoding='utf-8')
