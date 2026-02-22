"""Seed prompts from YAML files into PostgreSQL.

Reads all .yml files from the prompts/ directory and inserts them into the
prompts table if they don't already exist. This runs at app startup.
"""
import os
import uuid
import yaml
from pathlib import Path
from core.db.postgres import get_dict_connection
from core.logging import log_info, log_error, log_warning


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _infer_prompt_type(key: str) -> str:
    if key.endswith("_system"):
        return "system"
    elif key.endswith("_user"):
        return "user"
    return "template"


def seed_prompts_from_yaml():
    """Load all YAML prompt files and insert into DB if not already present."""
    conn = get_dict_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT prompt_key, category FROM prompts WHERE is_active = true")
        existing = {(row["prompt_key"], row["category"]) for row in cur.fetchall()}

        yml_files = sorted(PROMPTS_DIR.glob("*.yml"))
        if not yml_files:
            log_warning("No YAML prompt files found in prompts/", "prompt_seeder")
            return

        inserted = 0
        skipped = 0

        for yml_path in yml_files:
            category = yml_path.stem
            try:
                with open(yml_path, "r", encoding="utf-8") as f:
                    prompts = yaml.safe_load(f)
                if not isinstance(prompts, dict):
                    log_warning(f"Skipping {yml_path.name}: not a dict", "prompt_seeder")
                    continue

                for key, content in prompts.items():
                    if not isinstance(content, str):
                        continue

                    if (key, category) in existing:
                        skipped += 1
                        continue

                    prompt_id = str(uuid.uuid4())
                    prompt_type = _infer_prompt_type(key)

                    cur.execute("""
                        INSERT INTO prompts (id, prompt_key, category, content, prompt_type, is_active, version)
                        VALUES (%s, %s, %s, %s, %s, true, 1)
                        ON CONFLICT (prompt_key, category, version) DO NOTHING
                    """, (prompt_id, key, category, content, prompt_type))
                    inserted += 1

            except Exception as e:
                log_error(f"Error seeding {yml_path.name}: {e}", "prompt_seeder")

        conn.commit()
        log_info(f"Prompt seeding complete: {inserted} inserted, {skipped} already exist", "prompt_seeder")

    except Exception as e:
        log_error(f"Prompt seeding failed: {e}", "prompt_seeder")
        conn.rollback()
    finally:
        cur.close()
        conn.close()
