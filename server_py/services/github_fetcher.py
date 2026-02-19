"""GitHub repository fetching utilities."""
import os
import re
import base64
import asyncio
from typing import Optional, Dict
import httpx
from core.logging import log_info, log_error


def get_github_headers() -> Dict[str, str]:
    """Get GitHub API headers with optional authentication."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "DocuGen-AI",
    }
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch_repo_contents(repo_url: str) -> str:
    """Fetch repository contents from GitHub."""
    match = re.match(r"github\.com/([^/]+)/([^/]+)", repo_url.replace("https://", ""))
    if not match:
        raise ValueError("Invalid GitHub URL")

    owner = match.group(1)
    repo = match.group(2).replace(".git", "")
    headers = get_github_headers()

    async with httpx.AsyncClient(timeout=60.0) as client:
        repo_response = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        if repo_response.status_code != 200:
            raise ValueError(f"Failed to fetch repository: {repo_response.status_code}")
        repo_data = repo_response.json()

        default_branch = repo_data.get("default_branch", "main")

        tree_response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
            headers=headers
        )
        tree_data = {"tree": []}
        if tree_response.status_code == 200:
            tree_data = tree_response.json()

    code_extensions = [
        '.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.go', '.rs', '.rb', '.php',
        '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
        '.json', '.yaml', '.yml', '.toml', '.xml', '.md', '.txt',
        '.sql', '.graphql', '.prisma', '.env.example', '.gitignore',
        '.sh', '.bash', '.zsh', '.dockerfile', '.config.js', '.config.ts'
    ]

    def is_code_file(path: str) -> bool:
        path_lower = path.lower()
        if any(x in path_lower for x in ['node_modules/', '/dist/', '/build/', '/.git/', '/coverage/', '/.next/']):
            return False
        return any(path_lower.endswith(ext) for ext in code_extensions) or \
               '.' not in path.split('/')[-1] or \
               path_lower.endswith('dockerfile') or path_lower.endswith('makefile')

    all_files = [
        {"path": f["path"], "size": f.get("size", 0)}
        for f in tree_data.get("tree", [])
        if f.get("type") == "blob" and is_code_file(f["path"])
    ]

    def priority_order(path: str) -> int:
        lower = path.lower()
        if lower == 'readme.md': return 0
        if lower == 'package.json': return 1
        if any(x in lower for x in ['index.', 'main.', 'app.']): return 2
        if lower.startswith('src/'): return 3
        if '/components/' in lower: return 4
        if '/pages/' in lower: return 5
        if any(x in lower for x in ['/api/', '/routes/']): return 6
        if any(x in lower for x in ['/services/', '/hooks/']): return 7
        if any(x in lower for x in ['/utils/', '/lib/']): return 8
        if 'config' in lower: return 9
        return 10

    all_files.sort(key=lambda f: priority_order(f["path"]))

    files_to_fetch = all_files[:50]
    file_contents = []
    total_chars = 0
    max_total_chars = 100000

    async def fetch_file(file_path: str) -> Optional[Dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    if "content" in data:
                        decoded = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
                        return {"path": file_path, "content": decoded}
        except Exception as e:
            log_error(f"Error fetching {file_path}", "ai", e)
        return None

    for i in range(0, len(files_to_fetch), 10):
        if total_chars >= max_total_chars:
            break
        batch = files_to_fetch[i:i+10]
        results = await asyncio.gather(*[fetch_file(f["path"]) for f in batch])
        
        for result in results:
            if result and total_chars < max_total_chars:
                max_file_chars = 4000
                content = result["content"]
                if len(content) > max_file_chars:
                    content = content[:max_file_chars] + "\n... [truncated - file continues]"
                file_contents.append(f"\n=== FILE: {result['path']} ===\n{content}")
                total_chars += len(content)

    dir_structure = {}
    for f in all_files:
        parts = f["path"].split("/")
        dir_name = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
        if dir_name not in dir_structure:
            dir_structure[dir_name] = []
        dir_structure[dir_name].append(parts[-1])

    structure_text = "\n\n".join([
        f"{dir}/\n  " + "\n  ".join(files[:20]) + (f"\n  ... and {len(files) - 20} more files" if len(files) > 20 else "")
        for dir, files in list(dir_structure.items())[:30]
    ])

    log_info(f"Fetched {len(file_contents)} files, {total_chars} total characters for {owner}/{repo}", "ai")

    return f"""
=== REPOSITORY INFORMATION ===
Repository: {repo_data.get('full_name', '')}
Description: {repo_data.get('description') or 'No description provided'}
Primary Language: {repo_data.get('language') or 'Unknown'}
Stars: {repo_data.get('stargazers_count', 0)}
Forks: {repo_data.get('forks_count', 0)}
Topics: {', '.join(repo_data.get('topics', [])) or 'None'}
Default Branch: {default_branch}
License: {repo_data.get('license', {}).get('name') if repo_data.get('license') else 'Not specified'}
Total Files Analyzed: {len(file_contents)}

=== DIRECTORY STRUCTURE ===
{structure_text}

=== COMPLETE FILE CONTENTS ===
{"".join(file_contents)}
    """.strip()
