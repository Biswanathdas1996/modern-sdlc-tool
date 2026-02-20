import re
from pathlib import Path
from typing import Dict


def get_project_deps_context(repo_path: str, language: str) -> str:
    root = Path(repo_path)
    deps_info = ""
    if language == "python":
        for dep_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
            fp = root / dep_file
            if fp.exists():
                try:
                    text = fp.read_text(errors='ignore')[:3000]
                    deps_info += f"\n{dep_file}:\n{text}\n"
                except Exception:
                    pass
    elif language in ("javascript", "typescript"):
        pkg = root / "package.json"
        if pkg.exists():
            try:
                text = pkg.read_text(errors='ignore')[:3000]
                deps_info += f"\npackage.json:\n{text}\n"
            except Exception:
                pass
    elif language == "go":
        mod = root / "go.mod"
        if mod.exists():
            try:
                text = mod.read_text(errors='ignore')[:3000]
                deps_info += f"\ngo.mod:\n{text}\n"
            except Exception:
                pass
    return deps_info


def get_related_imports_context(filepath: str, content: str, source_files: Dict[str, str], language: str) -> str:
    imported_files = []
    if language == "python":
        for match in re.finditer(r'(?:from|import)\s+([\w.]+)', content):
            mod = match.group(1).replace('.', '/')
            candidates = [f"{mod}.py", f"{mod}/__init__.py"]
            for c in candidates:
                if c in source_files:
                    imported_files.append(c)
                    break
    elif language in ("javascript", "typescript"):
        for match in re.finditer(r'(?:require|from)\s*[(\s]["\']([./][^"\']+)', content):
            mod = match.group(1)
            for ext in ['.js', '.ts', '.jsx', '.tsx', '']:
                candidate = mod + ext
                candidate = str(Path(filepath).parent / candidate) if mod.startswith('.') else candidate
                normalized = str(Path(candidate))
                if normalized in source_files:
                    imported_files.append(normalized)
                    break

    context = ""
    for imp_file in imported_files[:3]:
        imp_content = source_files[imp_file][:2000]
        context += f"\nImported module ({imp_file}):\n```\n{imp_content}\n```\n"
    return context
