import logging
from pathlib import Path
from typing import Dict

from ..constants import (
    IGNORE_DIRS, TEST_DIRS, IGNORE_EXTENSIONS,
    SOURCE_EXTENSIONS, MAX_FILE_SIZE, MAX_FILES_FOR_ANALYSIS,
)
from ..utils.pattern_matcher import is_test_file_strict

logger = logging.getLogger(__name__)


def get_file_tree(repo_path: str, max_depth: int = 4) -> str:
    tree_lines = []
    root = Path(repo_path)

    def walk(path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        all_ignore = IGNORE_DIRS - TEST_DIRS
        dirs = [e for e in entries if e.is_dir() and e.name not in all_ignore and not e.name.startswith('.')]
        files = [e for e in entries if e.is_file() and e.suffix not in IGNORE_EXTENSIONS]

        for i, d in enumerate(dirs):
            connector = "└── " if i == len(dirs) - 1 and not files else "├── "
            tree_lines.append(f"{prefix}{connector}{d.name}/")
            ext = "    " if i == len(dirs) - 1 and not files else "│   "
            walk(d, prefix + ext, depth + 1)

        for i, f in enumerate(files[:30]):
            connector = "└── " if i == len(files[:30]) - 1 else "├── "
            tree_lines.append(f"{prefix}{connector}{f.name}")
        if len(files) > 30:
            tree_lines.append(f"{prefix}└── ... ({len(files) - 30} more files)")

    walk(root)
    return "\n".join(tree_lines[:500])


def collect_source_files(repo_path: str) -> Dict[str, str]:
    logger.info(f"Collecting source files from: {repo_path}")
    files = {}
    root = Path(repo_path)

    for fp in root.rglob('*'):
        if any(part in IGNORE_DIRS for part in fp.parts):
            continue
        if any(part in TEST_DIRS for part in fp.parts):
            continue
        if fp.is_file() and fp.suffix in SOURCE_EXTENSIONS:
            if is_test_file_strict(fp.name):
                continue
            rel = str(fp.relative_to(root))
            try:
                text = fp.read_text(errors='ignore')
                if len(text) > MAX_FILE_SIZE:
                    text = text[:MAX_FILE_SIZE] + "\n... (truncated)"
                files[rel] = text
            except Exception:
                pass
            if len(files) >= MAX_FILES_FOR_ANALYSIS:
                logger.info(f"Reached maximum file limit ({MAX_FILES_FOR_ANALYSIS}), stopping collection")
                break
    logger.info(f"Collected {len(files)} source files")
    return files


def read_key_files(repo_path: str) -> Dict[str, str]:
    key_files = [
        "README.md", "readme.md",
        "package.json", "requirements.txt", "pyproject.toml",
        "pom.xml", "build.gradle", "go.mod", "Cargo.toml",
        "setup.py", "setup.cfg",
    ]
    contents = {}
    root = Path(repo_path)
    for kf in key_files:
        fp = root / kf
        if fp.exists() and fp.is_file():
            try:
                text = fp.read_text(errors='ignore')
                if len(text) > MAX_FILE_SIZE:
                    text = text[:MAX_FILE_SIZE] + "\n... (truncated)"
                contents[kf] = text
            except Exception:
                pass
    return contents
