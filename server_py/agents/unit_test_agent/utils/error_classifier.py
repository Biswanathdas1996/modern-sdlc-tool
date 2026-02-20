import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def classify_test_error(error_output: str, language: str) -> Dict[str, str]:
    error_output_lower = error_output.lower()

    if re.search(r"cannot find module|modulenotfounderror|importerror|no module named|cannot resolve", error_output_lower):
        return {
            "type": "IMPORT_ERROR",
            "priority": "critical",
            "description": "Module import path is incorrect"
        }

    if re.search(r"is not a function|mockreturnvalue.*undefined|mock.*not defined|cannot read.*undefined", error_output_lower):
        return {
            "type": "MOCK_ERROR",
            "priority": "high",
            "description": "Mock not properly configured or defined after imports"
        }

    if re.search(r"is not a function|undefined.*function|attributeerror|has no attribute|is undefined", error_output_lower):
        return {
            "type": "ATTRIBUTE_ERROR",
            "priority": "high",
            "description": "Testing function/method that doesn't exist in source"
        }

    if re.search(r"promise|async|await|then.*catch|unhandledpromise", error_output_lower):
        return {
            "type": "ASYNC_ERROR",
            "priority": "medium",
            "description": "Async function not properly handled"
        }

    if re.search(r"syntaxerror|unexpected token|invalid syntax", error_output_lower):
        return {
            "type": "SYNTAX_ERROR",
            "priority": "critical",
            "description": "Code has syntax errors"
        }

    if re.search(r"expected.*received|assertionerror|expected.*to.*but|test failed", error_output_lower):
        return {
            "type": "ASSERTION_ERROR",
            "priority": "low",
            "description": "Test assertion logic is incorrect"
        }

    return {
        "type": "UNKNOWN",
        "priority": "medium",
        "description": "Unknown error type"
    }


def get_error_specific_guidance(error_type: str, filepath: str, language: str, repo_path: str = "") -> str:
    if error_type == "IMPORT_ERROR":
        return """**CRITICAL FIX NEEDED: Import path is wrong!**

ACTION REQUIRED:
1. Check the error message to see which import is failing
2. The test file needs to import from the source file
3. Use RELATIVE imports (e.g., '../api/APIService' or './APIService')
4. Remove file extensions in imports (use 'APIService' not 'APIService.js')
5. Count the directory levels carefully - each '../' goes up one level

EXAMPLE:
If test is at:    __tests__/api/APIService.test.js
And source is at: api/APIService.js
Then import:      import { APIService } from '../../api/APIService';

DO NOT use absolute imports like '/api/APIService' - they will fail!
"""

    elif error_type == "MOCK_ERROR":
        return """**CRITICAL FIX NEEDED: Mock configuration is broken!**

ACTION REQUIRED:
1. Move ALL jest.mock() calls to the VERY TOP of the file (line 1-5)
2. Mocks MUST be defined BEFORE any imports
3. Mock the MODULE PATH, not the imported variable

CORRECT ORDER:
```javascript
// 1. Mocks FIRST (top of file)
jest.mock('axios');
jest.mock('../services/api');

// 2. Then imports
import React from 'react';
import { APIService } from '../api/APIService';

// 3. Then tests
describe('APIService', () => {...});
```
"""

    elif error_type == "ATTRIBUTE_ERROR":
        return """**CRITICAL FIX NEEDED: Testing functions that don't exist!**

ACTION REQUIRED:
1. Read the SOURCE FILE above carefully
2. Only test functions/methods that ACTUALLY EXIST in the source
3. Check exact function names (case-sensitive)
4. Remove tests for functions you assumed exist but don't
"""

    elif error_type == "ASYNC_ERROR":
        return """**FIX NEEDED: Async/Promise handling is incorrect!**

ACTION REQUIRED:
1. If testing async function, mark test as async: it('test', async () => {
2. Use await before calling async functions
3. For React Testing Library: use waitFor() or findBy*() queries
4. Mock promises to resolve/reject properly
"""

    elif error_type == "SYNTAX_ERROR":
        return """**CRITICAL FIX: Syntax error in generated code!**

ACTION REQUIRED:
1. Check for missing brackets, parentheses, braces
2. Check for incorrect JSX syntax
3. Check for incorrect string quotes
4. Ensure proper async/await syntax
"""

    elif error_type == "ASSERTION_ERROR":
        return """**FIX NEEDED: Assertion values don't match actual behavior!**

ACTION REQUIRED:
1. Re-read the SOURCE CODE to understand what it actually does
2. Update expected values to match real behavior
3. If uncertain, use simpler assertions (e.g., toBeDefined() instead of exact values)
"""

    else:
        return """**General debugging needed - carefully review the error message and fix accordingly.**"""
