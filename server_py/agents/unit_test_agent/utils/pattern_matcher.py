import re
from pathlib import Path
from typing import Optional

from ..constants import IGNORE_DIRS, TEST_DIRS, LANGUAGE_TEST_CONFIG, SOURCE_EXTENSIONS


def is_test_file_strict(filename: str) -> bool:
    lower = filename.lower()
    if re.match(r'^test_.*\.\w+$', lower):
        return True
    if re.match(r'.*_test\.\w+$', lower):
        return True
    if re.match(r'.*\.test\.\w+$', lower):
        return True
    if re.match(r'.*\.spec\.\w+$', lower):
        return True
    if re.match(r'.*Test\.java$', filename):
        return True
    if re.match(r'.*Tests\.java$', filename):
        return True
    return False


def is_test_file_by_context(filepath: Path, language: str) -> bool:
    parts = set(filepath.parts)
    if parts & TEST_DIRS:
        return True
    if is_test_file_strict(filepath.name):
        return True
    config = LANGUAGE_TEST_CONFIG.get(language, {})
    for pattern in config.get("test_patterns", []):
        if re.match(pattern, filepath.name):
            return True
    return False


def infer_source_file(test_path: str, language: str, repo_path: str) -> Optional[str]:
    tp = Path(test_path)
    name = tp.stem
    root = Path(repo_path)

    if language == "python":
        source_name = re.sub(r'^test_', '', name)
        source_name = re.sub(r'_test$', '', source_name)
        candidates = []
        candidates.append(f"{source_name}.py")
        candidates.append(f"src/{source_name}.py")
        if '_' in source_name:
            parts = source_name.split('_')
            for i in range(1, len(parts)):
                dir_part = "/".join(parts[:i])
                file_part = "_".join(parts[i:])
                candidates.append(f"{dir_part}/{file_part}.py")
                candidates.append(f"src/{dir_part}/{file_part}.py")

    elif language in ("javascript", "typescript"):
        ext = ".ts" if language == "typescript" else ".js"
        tsx_ext = ".tsx" if language == "typescript" else ".jsx"
        source_name = re.sub(r'\.(test|spec)$', '', name)
        parent_dir = str(tp.parent)
        mirror_dir = re.sub(r'(^|/)(__tests__|tests?|specs?)(/|$)', r'\1', parent_dir).strip('/')
        candidates = [
            f"src/{source_name}{ext}",
            f"lib/{source_name}{ext}",
            f"{source_name}{ext}",
            f"src/{source_name}{tsx_ext}",
            f"{source_name}{tsx_ext}",
        ]
        if mirror_dir:
            candidates.insert(0, f"{mirror_dir}/{source_name}{ext}")
            candidates.insert(1, f"{mirror_dir}/{source_name}{tsx_ext}")

    elif language == "go":
        source_name = re.sub(r'_test$', '', name)
        candidates = [
            str(tp.parent / f"{source_name}.go"),
        ]

    elif language == "java":
        source_name = re.sub(r'Tests?$', '', name)
        parent_str = str(tp.parent)
        main_path = parent_str.replace("src/test/java", "src/main/java")
        candidates = [
            f"{main_path}/{source_name}.java" if main_path != parent_str else f"{source_name}.java",
            f"src/main/java/{source_name}.java",
            f"{source_name}.java",
        ]

    else:
        source_name = re.sub(r'^test_', '', name)
        candidates = [f"{source_name}{tp.suffix}", f"src/{source_name}{tp.suffix}"]

    for candidate in candidates:
        candidate = candidate.lstrip('/')
        if (root / candidate).exists():
            return candidate

    target_name = candidates[0].split('/')[-1] if candidates else name + tp.suffix
    found = []
    for fp in root.rglob(target_name):
        if any(part in IGNORE_DIRS for part in fp.parts):
            continue
        if any(part in TEST_DIRS for part in fp.parts):
            continue
        if not is_test_file_strict(fp.name):
            found.append(str(fp.relative_to(root)))

    if len(found) == 1:
        return found[0]

    return None
