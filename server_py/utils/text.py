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
