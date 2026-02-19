import logging
import sys

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [UnitTestAgent] %(message)s',
        datefmt='%I:%M:%S %p'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

MAX_FIX_ATTEMPTS = 2
IGNORE_DIRS = {
    '.git', 'node_modules', '__pycache__', '.next', 'dist', 'build',
    '.venv', 'venv', 'env', '.env', '.idea', '.vscode', 'vendor',
    'target', 'bin', 'obj', '.cache', '.nuxt', '.output', 'coverage',
    '.pytest_cache', '.mypy_cache', 'eggs', '*.egg-info',
}

TEST_DIRS = {'test', 'tests', '__tests__', 'spec', 'specs'}

IGNORE_EXTENSIONS = {
    '.pyc', '.pyo', '.class', '.o', '.so', '.dll', '.exe',
    '.ico', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp',
    '.mp3', '.mp4', '.wav', '.avi', '.mov',
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.woff', '.woff2', '.ttf', '.eot',
    '.lock', '.min.js', '.min.css',
}

SOURCE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
    '.rb', '.php', '.cs', '.cpp', '.c', '.h', '.hpp',
    '.swift', '.kt', '.scala', '.ex', '.exs',
    '.vue', '.svelte',
}

MAX_FILE_SIZE = 100_000
MAX_FILES_FOR_ANALYSIS = 80
MAX_EXISTING_TEST_SAMPLE_SIZE = 6000

LANGUAGE_TEST_CONFIG = {
    "python": {
        "framework": "pytest",
        "test_dir": "tests",
        "file_prefix": "test_",
        "file_ext": ".py",
        "import_style": "from {module} import {name}",
        "test_patterns": [r'^test_.*\.py$', r'.*_test\.py$'],
    },
    "javascript": {
        "framework": "jest",
        "test_dir": "__tests__",
        "file_suffix": ".test",
        "file_ext": ".js",
        "import_style": "const {{ {name} }} = require('{module}');",
        "test_patterns": [r'.*\.test\.js$', r'.*\.spec\.js$', r'^test_.*\.js$'],
    },
    "typescript": {
        "framework": "jest",
        "test_dir": "__tests__",
        "file_suffix": ".test",
        "file_ext": ".ts",
        "import_style": "import {{ {name} }} from '{module}';",
        "test_patterns": [r'.*\.test\.ts$', r'.*\.test\.tsx$', r'.*\.spec\.ts$'],
    },
    "java": {
        "framework": "JUnit 5",
        "test_dir": "src/test/java",
        "file_suffix": "Test",
        "file_ext": ".java",
        "test_patterns": [r'.*Test\.java$', r'.*Tests\.java$', r'.*Spec\.java$'],
    },
    "go": {
        "framework": "testing",
        "test_dir": "",
        "file_suffix": "_test",
        "file_ext": ".go",
        "test_patterns": [r'.*_test\.go$'],
    },
}
