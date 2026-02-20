"""JSON parsing utilities."""
import json
import re
from typing import Any


def _fix_json_escape_sequences(text: str) -> str:
    r"""Fix invalid escape sequences in JSON strings.
    
    Replaces backslashes that are not part of valid JSON escape sequences.
    Valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
    """
    result = []
    i = 0
    in_string = False
    
    while i < len(text):
        char = text[i]
        
        # Track if we're inside a string
        if char == '"' and (i == 0 or text[i-1] != '\\'):
            in_string = not in_string
            result.append(char)
            i += 1
            continue
        
        # Only fix escapes inside strings
        if in_string and char == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            # Check if it's a valid escape sequence
            if next_char in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't'):
                result.append(char)
                i += 1
            elif next_char == 'u' and i + 5 < len(text):
                # Check for \uXXXX pattern
                hex_part = text[i+2:i+6]
                if all(c in '0123456789abcdefABCDEF' for c in hex_part):
                    result.append(char)
                    i += 1
                else:
                    # Invalid unicode escape, escape the backslash
                    result.append('\\\\')
                    i += 1
            else:
                # Invalid escape sequence, escape the backslash
                result.append('\\\\')
                i += 1
        else:
            result.append(char)
            i += 1
    
    return ''.join(result)


def _remove_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing brackets/braces in JSON.
    
    Handles cases like:
    - [1, 2, 3,] -> [1, 2, 3]
    - {"key": "value",} -> {"key": "value"}
    """
    # Remove trailing commas before } or ]
    # This regex matches comma followed by optional whitespace and then } or ]
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def _fix_common_json_issues(text: str) -> str:
    """Fix common JSON formatting issues from AI responses."""
    # Remove trailing commas
    text = _remove_trailing_commas(text)
    
    # Fix escape sequences
    text = _fix_json_escape_sequences(text)
    
    return text


def parse_json_response(text: str) -> Any:
    """Parse JSON from AI response, handling various formats and common issues."""
    cleaned = text.strip()
    
    # Remove markdown code blocks
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    cleaned = cleaned.strip()
    
    # Try direct parsing first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        # Try to fix common JSON issues (trailing commas, escape sequences)
        try:
            fixed = _fix_common_json_issues(cleaned)
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Try regex extraction for JSON object
        object_match = re.search(r'\{[\s\S]*\}', text)
        if object_match:
            try:
                extracted = object_match.group(0)
                fixed = _fix_common_json_issues(extracted)
                return json.loads(fixed)
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Try regex extraction for JSON array
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                extracted = array_match.group(0)
                fixed = _fix_common_json_issues(extracted)
                return json.loads(fixed)
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Raise original error if all attempts fail
        preview = text[:200] + "..." if len(text) > 200 else text
        raise ValueError(
            f"Failed to parse JSON from response. "
            f"Original error: {first_error}. "
            f"Response preview: {preview}"
        )


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks with section-aware boundaries.
    
    Preserves document structure by preferring to break at:
    1. Section headings (lines starting with # or all-caps lines)
    2. Double newlines (paragraph boundaries)
    3. Single newlines
    4. Sentence endings (period followed by space or newline)
    5. Any position as last resort
    
    Args:
        text: The full document text to chunk
        chunk_size: Target size for each chunk in characters (default: 1500)
        overlap: Number of overlapping characters between chunks (default: 200)
    
    Returns:
        List of text chunks covering the entire document
    """
    if not text or not text.strip():
        return []
    
    text = text.strip()
    
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        
        if end >= text_len:
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break
        
        best_break = -1
        
        search_start = start + chunk_size // 3
        search_region = text[search_start:end]
        
        heading_patterns = ['\n# ', '\n## ', '\n### ', '\n#### ']
        for pattern in heading_patterns:
            idx = search_region.rfind(pattern)
            if idx != -1:
                best_break = search_start + idx + 1
                break
        
        if best_break == -1:
            idx = search_region.rfind('\n\n')
            if idx != -1:
                best_break = search_start + idx + 2
        
        if best_break == -1:
            idx = search_region.rfind('\n')
            if idx != -1:
                best_break = search_start + idx + 1
        
        if best_break == -1:
            for sep in ['. ', '? ', '! ']:
                idx = search_region.rfind(sep)
                if idx != -1:
                    candidate = search_start + idx + len(sep)
                    if best_break == -1 or candidate > best_break:
                        best_break = candidate
        
        if best_break > start:
            end = best_break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = max(end - overlap, start + 1)
    
    return chunks
