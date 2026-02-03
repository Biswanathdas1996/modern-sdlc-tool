"""JSON parsing utilities."""
import json
import re
from typing import Any


def parse_json_response(text: str) -> Any:
    """Parse JSON from AI response, handling various formats."""
    cleaned = text.strip()
    
    # Remove markdown code blocks
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    # Try direct parsing first
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as first_error:
        # Try regex extraction for JSON object
        object_match = re.search(r'\{[\s\S]*\}', text)
        if object_match:
            try:
                return json.loads(object_match.group(0))
            except:
                pass
        
        # Try regex extraction for JSON array
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                return json.loads(array_match.group(0))
            except:
                pass
        
        # Raise original error if all attempts fail
        preview = text[:200] + "..." if len(text) > 200 else text
        raise ValueError(
            f"Failed to parse JSON from response. "
            f"Original error: {first_error}. "
            f"Response preview: {preview}"
        )


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence or newline
        if end < len(text):
            last_period = text.rfind(".", start, end)
            last_newline = text.rfind("\n", start, end)
            break_point = max(last_period, last_newline)
            
            if break_point > start + chunk_size // 2:
                end = break_point + 1
        
        chunk = text[start:min(end, len(text))].strip()
        if len(chunk) > 50:  # Only add substantial chunks
            chunks.append(chunk)
        
        start = end - overlap
        
        if start >= len(text) - overlap:
            break
    
    return chunks
