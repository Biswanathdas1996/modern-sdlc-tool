import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, List


def check_command_exists(command: str) -> bool:
    try:
        if os.name == 'nt':
            result = subprocess.run(
                ["where", command],
                capture_output=True, text=True, timeout=5
            )
        else:
            result = subprocess.run(
                ["which", command],
                capture_output=True, text=True, timeout=5
            )
        return result.returncode == 0
    except Exception:
        return False


def run_npm_command(args: List[str], cwd: str, timeout: int = 300, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    if os.name == 'nt':
        cmd = ' '.join(args)
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            env=env or os.environ.copy()
        )
    else:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )


def is_cra_project(repo_path: str) -> bool:
    pkg_path = Path(repo_path) / "package.json"
    if pkg_path.exists():
        try:
            with open(pkg_path, 'r') as f:
                pkg = json.load(f)
            scripts = pkg.get("scripts", {})
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            return "react-scripts" in deps or "react-scripts test" in scripts.get("test", "")
        except Exception:
            pass
    return False
