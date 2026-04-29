"""Shared helpers for codeprobe scripts.

Canonical definitions lifted from file_stats.py so file_stats.py,
dependency_mapper.py, and complexity_scorer.py can share file traversal
without drift.
"""

from __future__ import annotations

import os
import re


# Directories to skip during traversal
SKIP_DIRS: set[str] = {
    "node_modules",
    "vendor",
    ".git",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".venv",
    "venv",
    "env",
}

# Recognized source file extensions
RECOGNIZED_EXTENSIONS: set[str] = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".php",
    ".java",
    ".rb",
    ".go",
    ".rs",
    ".vue",
    ".svelte",
    ".sql",
    ".sh",
    ".css",
    ".scss",
    ".html",
}

# Method/function definition patterns. Each variant captures the function's
# identifier under the group name "name" — callers that only need a boolean
# match (e.g., file_stats.count_methods) can ignore the group; callers that
# need the identifier (e.g., complexity_scorer._match_function) read it via
# m.group("name").
METHOD_PATTERNS: list[re.Pattern] = [
    # Python
    re.compile(r"^\s*def\s+(?P<name>\w+)"),
    # JavaScript/TypeScript/PHP named functions
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)"),
    # PHP class methods
    re.compile(r"^\s*(?:public|private|protected)\s+(?:static\s+)?function\s+(?P<name>\w+)"),
    # Java/TypeScript class methods (public/private/protected return_type methodName)
    re.compile(
        r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:async\s+)?\w+\s+(?P<name>\w+)\s*\("
    ),
    # Rust functions
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)"),
    # Go functions (optional receiver in parens, then name)
    re.compile(r"^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(?P<name>\w+)"),
    # Ruby methods
    re.compile(r"^\s*def\s+(?P<name>\w+)"),
    # Arrow functions assigned to const/let/var at class level (heuristic)
    re.compile(r"^\s*(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?:async\s+)?\(.*\)\s*=>"),
]


MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5 MB


def is_binary(filepath: str) -> bool:
    """Detect binary files by checking for null bytes in the first 1024 bytes."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except (OSError, IOError):
        return True


def collect_files(root_dir: str) -> list[str]:
    """Walk the directory tree and collect recognized source files."""
    files: list[str] = []
    root = os.path.abspath(root_dir)

    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out skip directories (modifying dirnames in-place prunes the walk)
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in RECOGNIZED_EXTENSIONS:
                continue

            full_path = os.path.join(dirpath, filename)

            # Skip symlinks that escape the project root
            real = os.path.realpath(full_path)
            try:
                if os.path.commonpath([real, root]) != root:
                    continue
            except ValueError:
                continue

            # Skip binary files
            if is_binary(full_path):
                continue

            # Store as relative path from root_dir
            rel_path = os.path.relpath(full_path, root)
            files.append(rel_path)

    return sorted(files)
