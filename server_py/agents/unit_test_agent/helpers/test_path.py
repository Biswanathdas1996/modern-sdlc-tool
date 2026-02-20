from pathlib import Path
from typing import Dict, Any, Optional

from ..constants import LANGUAGE_TEST_CONFIG


def determine_test_path(source_file: str, language: str, repo_path: str, tech_stack: Optional[Dict[str, Any]] = None) -> str:
    config = LANGUAGE_TEST_CONFIG.get(language, LANGUAGE_TEST_CONFIG["python"])
    source_path = Path(source_file)
    stem = source_path.stem
    ext = config.get("file_ext", source_path.suffix)

    test_location = tech_stack.get("test_location", "separate-dir") if tech_stack else "separate-dir"

    if language == "python":
        test_filename = f"{config.get('file_prefix', 'test_')}{stem}{ext}"
        test_dir = config["test_dir"]
        if str(source_path.parent) != ".":
            sub_dir = str(source_path.parent).replace("/", "_").replace("\\", "_")
            test_filename = f"test_{sub_dir}_{stem}{ext}"
        return str(Path(test_dir) / test_filename)

    elif language in ("javascript", "typescript"):
        suffix = config.get("file_suffix", ".test")
        test_filename = f"{stem}{suffix}{ext}"

        if test_location == "next-to-source":
            return str(source_path.parent / test_filename)
        elif test_location == "mirror-structure":
            if str(source_path.parent).startswith("src"):
                rel_path = source_path.parent
                return str(Path("__tests__") / rel_path / test_filename)
            else:
                return str(Path("__tests__") / test_filename)
        else:
            test_dir = config["test_dir"]
            return str(Path(test_dir) / test_filename)

    elif language == "go":
        test_filename = f"{stem}_test{ext}"
        return str(source_path.parent / test_filename)

    elif language == "java":
        test_filename = f"{stem}Test{ext}"
        test_dir = config["test_dir"]
        pkg_path = str(source_path.parent)
        if pkg_path.startswith("src/main/java"):
            pkg_path = pkg_path.replace("src/main/java", "", 1).lstrip("/")
        return str(Path(test_dir) / pkg_path / test_filename)

    else:
        test_filename = f"test_{stem}{ext}"
        return str(Path("tests") / test_filename)
