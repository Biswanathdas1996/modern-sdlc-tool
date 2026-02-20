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


def _split_into_sections(text: str) -> list[str]:
    """Split text into logical sections based on headings and titled lines.
    
    Detects section boundaries at:
    - Markdown headings (# Title)
    - Title-case lines followed by newlines (e.g. "Customer Onboarding Workflow")
    - Lines ending with "Workflow", "Process", "Procedure", etc.
    """
    lines = text.split('\n')
    sections = []
    current_section_lines = []
    
    heading_pattern = re.compile(
        r'^(#{1,6}\s+.+|'
        r'[A-Z][A-Za-z0-9\s/()&,\-]+\s+(Workflow|Process|Procedure|Policy|Standard|Audit|Review|Assessment|Check|Module|Phase|Stage|Step)s?\s*$|'
        r'[A-Z][A-Za-z0-9\s/()&,\-]+(Workflow|Process|Procedure|Policy|Standard|Audit|Review|Assessment|Check|Module|Phase|Stage|Step)s?\s*$)',
        re.MULTILINE
    )
    
    for line in lines:
        stripped = line.strip()
        if stripped and heading_pattern.match(stripped) and current_section_lines:
            section_text = '\n'.join(current_section_lines).strip()
            if section_text:
                sections.append(section_text)
            current_section_lines = [line]
        else:
            current_section_lines.append(line)
    
    if current_section_lines:
        section_text = '\n'.join(current_section_lines).strip()
        if section_text:
            sections.append(section_text)
    
    return sections


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split text into chunks that respect section/heading boundaries.
    
    Strategy:
    1. First split text into logical sections (by headings/titles)
    2. If a section fits in chunk_size, keep it as one chunk
    3. If a section is too large, split it at paragraph/sentence boundaries
    4. Merge small consecutive sections into one chunk if they fit together
    
    Args:
        text: The full document text to chunk
        chunk_size: Target size for each chunk in characters (default: 500)
        overlap: Number of overlapping characters between chunks (default: 100)
    
    Returns:
        List of text chunks covering the entire document
    """
    if not text or not text.strip():
        return []
    
    text = text.strip()
    
    if len(text) <= chunk_size:
        return [text]
    
    sections = _split_into_sections(text)
    
    if len(sections) <= 1:
        return _chunk_by_size(text, chunk_size, overlap)
    
    chunks = []
    buffer = ""
    
    for section in sections:
        if len(section) > chunk_size:
            if buffer.strip():
                chunks.append(buffer.strip())
                buffer = ""
            sub_chunks = _chunk_by_size(section, chunk_size, overlap)
            chunks.extend(sub_chunks)
        elif len(buffer) + len(section) + 2 <= chunk_size:
            buffer = (buffer + "\n\n" + section).strip() if buffer else section
        else:
            if buffer.strip():
                chunks.append(buffer.strip())
            buffer = section
    
    if buffer.strip():
        chunks.append(buffer.strip())
    
    return chunks


def _chunk_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fallback: split text by size with overlap, breaking at natural boundaries."""
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
