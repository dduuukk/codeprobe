#!/usr/bin/env python3
"""
file_stats.py — Codebase statistics for codeprobe.

Analyzes source files in a directory and outputs JSON to stdout.
Read-only: only reads files, never writes anything.
Dependencies: Python 3.8+ standard library only.

Usage:
    python3 file_stats.py /path/to/project
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from _common import (
    METHOD_PATTERNS,
    MAX_FILE_SIZE,
    collect_files,
)

# Patterns for test file detection
TEST_DIR_NAMES: set[str] = {"test", "tests", "__tests__", "spec"}
TEST_FILE_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:^test_|_test\.|\.test\.|Test[A-Z])", re.IGNORECASE),
    re.compile(r"(?:^spec_|_spec\.|\.spec\.)", re.IGNORECASE),
]

# Comment line patterns (basic heuristic)
COMMENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*//"),       # C-style single-line
    re.compile(r"^\s*#"),        # Python, Ruby, Shell, etc.
    re.compile(r"^\s*/\*"),      # C-style block open
    re.compile(r"^\s*\*"),       # C-style block continuation
    re.compile(r'^\s*"""'),      # Python docstring
    re.compile(r"^\s*'''"),      # Python docstring (single-quote)
]

# Class definition patterns by language
CLASS_PATTERNS: list[re.Pattern] = [
    # Python, PHP, Java, TypeScript, JavaScript
    re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+\w+"),
    # Rust struct
    re.compile(r"^\s*(?:pub\s+)?struct\s+\w+"),
    # Rust impl
    re.compile(r"^\s*(?:pub\s+)?impl\s+"),
    # Go struct
    re.compile(r"^\s*type\s+\w+\s+struct\b"),
]


def is_test_file(filepath: str) -> bool:
    """Determine if a file is a test file based on path and name patterns."""
    parts = Path(filepath).parts
    # Check if any directory component is a test directory
    for part in parts:
        if part.lower() in TEST_DIR_NAMES:
            return True
    # Check filename against test patterns
    filename = os.path.basename(filepath)
    for pattern in TEST_FILE_PATTERNS:
        if pattern.search(filename):
            return True
    return False


def is_comment_line(line: str) -> bool:
    """Check if a line is a comment (basic heuristic)."""
    for pattern in COMMENT_PATTERNS:
        if pattern.match(line):
            return True
    return False


def count_classes(line: str) -> int:
    """Count class definitions on a line."""
    for pattern in CLASS_PATTERNS:
        if pattern.match(line):
            return 1
    return 0


def count_methods(line: str) -> int:
    """Count method/function definitions on a line."""
    for pattern in METHOD_PATTERNS:
        if pattern.match(line):
            return 1
    return 0


def analyze_file(filepath: str) -> dict[str, Any] | None:
    """Analyze a single source file and return its statistics."""
    try:
        if os.path.getsize(filepath) > MAX_FILE_SIZE:
            return None
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except PermissionError:
        return None
    except (OSError, IOError):
        return None

    loc = 0
    blank_lines = 0
    comment_lines = 0
    class_count = 0
    method_count = 0

    for line in lines:
        stripped = line.rstrip("\n\r")
        if stripped.strip() == "":
            blank_lines += 1
        elif is_comment_line(stripped):
            comment_lines += 1
            loc += 1
        else:
            loc += 1

        class_count += count_classes(stripped)
        method_count += count_methods(stripped)

    return {
        "file": filepath,
        "loc": loc,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "class_count": class_count,
        "method_count": method_count,
    }


def compute_summary(file_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics from per-file entries."""
    total_files = len(file_entries)

    if total_files == 0:
        return {
            "total_files": 0,
            "total_loc": 0,
            "total_blank_lines": 0,
            "total_comment_lines": 0,
            "avg_file_loc": 0.0,
            "avg_method_length": 0.0,
            "largest_file": {"file": "", "loc": 0},
            "most_methods": {"file": "", "method_count": 0},
            "test_file_count": 0,
            "test_file_ratio": 0.0,
            "comment_ratio": 0.0,
            "files_over_300_loc": 0,
            "files_over_500_loc": 0,
        }

    total_loc = sum(e["loc"] for e in file_entries)
    total_blank = sum(e["blank_lines"] for e in file_entries)
    total_comments = sum(e["comment_lines"] for e in file_entries)
    total_methods = sum(e["method_count"] for e in file_entries)

    avg_file_loc = round(total_loc / total_files, 1)
    avg_method_length = round(total_loc / total_methods, 1) if total_methods > 0 else 0.0

    largest = max(file_entries, key=lambda e: e["loc"])
    most_methods_entry = max(file_entries, key=lambda e: e["method_count"])

    test_count = sum(1 for e in file_entries if is_test_file(e["file"]))
    test_ratio = round(test_count / total_files, 3) if total_files > 0 else 0.0

    comment_ratio = round(total_comments / total_loc, 3) if total_loc > 0 else 0.0

    files_over_300 = sum(1 for e in file_entries if e["loc"] > 300)
    files_over_500 = sum(1 for e in file_entries if e["loc"] > 500)

    return {
        "total_files": total_files,
        "total_loc": total_loc,
        "total_blank_lines": total_blank,
        "total_comment_lines": total_comments,
        "avg_file_loc": avg_file_loc,
        "avg_method_length": avg_method_length,
        "largest_file": {"file": largest["file"], "loc": largest["loc"]},
        "most_methods": {
            "file": most_methods_entry["file"],
            "method_count": most_methods_entry["method_count"],
        },
        "test_file_count": test_count,
        "test_file_ratio": test_ratio,
        "comment_ratio": comment_ratio,
        "files_over_300_loc": files_over_300,
        "files_over_500_loc": files_over_500,
    }


def main() -> None:
    if len(sys.argv) < 2:
        json.dump(
            {"error": "Usage: python3 file_stats.py /path/to/project"},
            sys.stdout,
            indent=2,
        )
        sys.exit(1)

    target_dir = os.path.realpath(sys.argv[1])

    if not os.path.isdir(target_dir):
        json.dump(
            {"error": f"Directory not found: {target_dir}"},
            sys.stdout,
            indent=2,
        )
        sys.exit(1)

    # Collect and analyze files
    file_paths = collect_files(target_dir)
    root = os.path.abspath(target_dir)
    file_entries: list[dict[str, Any]] = []

    for rel_path in file_paths:
        full_path = os.path.join(root, rel_path)
        result = analyze_file(full_path)
        if result is not None:
            result["file"] = rel_path
            file_entries.append(result)

    summary = compute_summary(file_entries)

    output = {
        "files": file_entries,
        "summary": summary,
    }

    json.dump(output, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
