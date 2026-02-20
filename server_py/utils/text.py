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


def _repair_truncated_json(text: str):
    """Attempt to repair a truncated JSON array by closing it at the last complete object."""
    stripped = text.strip()
    if not stripped.startswith("["):
        return None

    last_close_brace = stripped.rfind("}")
    if last_close_brace <= 0:
        return None

    candidate = stripped[:last_close_brace + 1].rstrip().rstrip(",") + "\n]"
    try:
        fixed = _fix_common_json_issues(candidate)
        result = json.loads(fixed)
        if isinstance(result, list) and len(result) > 0:
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


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
        
        # Try to repair truncated JSON arrays (common when AI hits token limit)
        repaired = _repair_truncated_json(cleaned)
        if repaired is not None:
            return repaired

        # Raise original error if all attempts fail
        preview = text[:200] + "..." if len(text) > 200 else text
        raise ValueError(
            f"Failed to parse JSON from response. "
            f"Original error: {first_error}. "
            f"Response preview: {preview}"
        )


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs using structural cues.
    
    Detects paragraph boundaries at:
    1. Blank lines (standard paragraph separator)
    2. Section title lines - a non-bullet, non-indented line that appears
       after a bullet/list item, indicating a new topic/section starts
    3. Markdown headings (# Title)
    
    This handles documents where sections aren't separated by blank lines
    (common with PDF extraction).
    """
    lines = text.split('\n')
    paragraphs = []
    current_lines = []
    
    prev_was_list_item = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped == '':
            if current_lines:
                para = '\n'.join(current_lines).strip()
                if para:
                    paragraphs.append(para)
                current_lines = []
            prev_was_list_item = False
            continue
        
        is_list_item = stripped.startswith(('- ', '* ', '• ')) or re.match(r'^\d+[\.\)]\s', stripped)
        is_heading = stripped.startswith('#')
        is_title_line = (
            not is_list_item 
            and not is_heading
            and len(stripped) > 3
            and not stripped[0].islower()
        )
        
        if current_lines and (is_heading or (prev_was_list_item and is_title_line)):
            para = '\n'.join(current_lines).strip()
            if para:
                paragraphs.append(para)
            current_lines = [line]
        else:
            current_lines.append(line)
        
        prev_was_list_item = is_list_item
    
    if current_lines:
        para = '\n'.join(current_lines).strip()
        if para:
            paragraphs.append(para)
    
    return paragraphs


def _split_long_paragraph(text: str, chunk_size: int) -> list[str]:
    """Split a single long paragraph at sentence boundaries.
    
    For paragraphs that exceed chunk_size, break at sentence endings
    (. ? !) or newlines, keeping each piece under the limit.
    """
    if len(text) <= chunk_size:
        return [text]
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current = ""
    
    for sentence in sentences:
        if not sentence.strip():
            continue
        
        if len(sentence) > chunk_size:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(sentence), chunk_size):
                piece = sentence[i:i + chunk_size].strip()
                if piece:
                    chunks.append(piece)
            continue
        
        if current and len(current) + len(sentence) + 1 > chunk_size:
            chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence
    
    if current.strip():
        chunks.append(current.strip())
    
    return chunks


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split text into chunks using paragraph-based strategy.
    
    Strategy:
    1. Split text into paragraphs (by blank lines)
    2. Each paragraph stays intact as one chunk if it fits
    3. Long paragraphs are split at sentence boundaries
    4. Small consecutive paragraphs are merged together (up to chunk_size)
    
    This keeps related content together and avoids cutting
    mid-sentence or mid-topic.
    
    Args:
        text: The full document text to chunk
        chunk_size: Max size for each chunk in characters (default: 500)
        overlap: Not used in paragraph mode (kept for API compatibility)
    
    Returns:
        List of text chunks covering the entire document
    """
    if not text or not text.strip():
        return []
    
    text = text.strip()
    
    if len(text) <= chunk_size:
        return [text]
    
    paragraphs = _split_into_paragraphs(text)
    
    if not paragraphs:
        return [text]
    
    units = []
    for para in paragraphs:
        if len(para) > chunk_size:
            units.extend(_split_long_paragraph(para, chunk_size))
        else:
            units.append(para)
    
    chunks = []
    buffer = ""
    
    for unit in units:
        if buffer and len(buffer) + len(unit) + 2 > chunk_size:
            chunks.append(buffer.strip())
            buffer = unit
        else:
            buffer = (buffer + "\n\n" + unit).strip() if buffer else unit
    
    if buffer.strip():
        chunks.append(buffer.strip())
    
    return chunks
