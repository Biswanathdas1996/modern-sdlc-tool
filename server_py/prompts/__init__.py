"""Prompt management — loads prompts from PostgreSQL (primary) with YAML fallback."""
import os
import yaml
import time
from typing import Dict, Any, Optional
from pathlib import Path


class PromptLoader:
    """Load and manage prompts from PostgreSQL with YAML file fallback."""

    def __init__(self):
        self.prompts_dir = Path(__file__).parent
        self._yaml_cache: Dict[str, Dict[str, Any]] = {}
        self._db_cache: Dict[str, str] = {}
        self._db_cache_ts: float = 0
        self._cache_ttl: float = 300

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        if filename in self._yaml_cache:
            return self._yaml_cache[filename]

        file_path = self.prompts_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            prompts = yaml.safe_load(f)

        self._yaml_cache[filename] = prompts
        return prompts

    def _get_from_db(self, category: str, key: str) -> Optional[str]:
        cache_key = f"{category}:{key}"

        now = time.time()
        if now - self._db_cache_ts < self._cache_ttl and cache_key in self._db_cache:
            return self._db_cache[cache_key]

        try:
            from core.db.postgres import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            try:
                cur.execute("""
                    SELECT content FROM prompts
                    WHERE prompt_key = %s AND category = %s AND is_active = true
                    ORDER BY version DESC LIMIT 1
                """, (key, category))
                row = cur.fetchone()
                if row:
                    self._db_cache[cache_key] = row["content"]
                    self._db_cache_ts = now
                    return row["content"]
            finally:
                cur.close()
                conn.close()
        except Exception:
            pass

        return None

    def invalidate_cache(self, category: str = None, key: str = None):
        if category and key:
            cache_key = f"{category}:{key}"
            self._db_cache.pop(cache_key, None)
        else:
            self._db_cache.clear()
        self._db_cache_ts = 0

    def load_prompts(self, filename: str) -> Dict[str, Any]:
        return self._load_yaml(filename)

    def get_prompt(self, filename: str, key: str) -> str:
        category = filename.replace(".yml", "").replace(".yaml", "")

        db_content = self._get_from_db(category, key)
        if db_content is not None:
            return db_content

        prompts = self._load_yaml(filename)
        if key not in prompts:
            raise KeyError(f"Prompt key '{key}' not found in {filename}")

        return prompts[key]


prompt_loader = PromptLoader()
