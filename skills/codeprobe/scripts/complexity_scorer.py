#!/usr/bin/env python3
"""
complexity_scorer.py — Cyclomatic complexity analysis for codeprobe.

Calculates cyclomatic complexity per function/method across a codebase
and outputs JSON to stdout.
Read-only: only reads files, never writes anything.
Dependencies: Python 3.8+ standard library only.

Usage:
    python3 complexity_scorer.py /path/to/project
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from _common import (
    MAX_FILE_SIZE,
    METHOD_PATTERNS,
    collect_files,
)

INDENT_LANGUAGES: Set[str] = {".py"}
BRACE_LANGUAGES: Set[str] = {".js", ".ts", ".jsx", ".tsx", ".php", ".java", ".go", ".rs"}

# Decision point patterns — each match adds 1 to base complexity of 1
DECISION_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(?:if|elif|elsif)\b"),
    re.compile(r"\belse\s+if\b"),
    re.compile(r"\b(?:for|while)\b"),
    re.compile(r"\bdo\b(?:\s*\{|\s*$)"),
    re.compile(r"\bcase\b"),
    re.compile(r"\b(?:catch|except|rescue)\b"),
]

LOGICAL_OP_PATTERN: re.Pattern = re.compile(r"&&|\|\|")
PYTHON_LOGICAL_PATTERN: re.Pattern = re.compile(r"\b(?:and|or)\b")
TERNARY_PATTERN: re.Pattern = re.compile(r"(?<!\w)\?(?!\?)")
NULL_COALESCE_PATTERN: re.Pattern = re.compile(r"\?\?")


def _match_function(line: str) -> Optional[str]:
    """Return the function name if the line declares a function, else None."""
    for pattern in METHOD_PATTERNS:
        m = pattern.match(line)
        if m:
            return m.group("name")
    return None


def _indent_level(line: str) -> int:
    """Return the number of leading spaces (tabs expanded to 4 spaces)."""
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def _strip_strings_and_comments(line: str) -> str:
    """Remove string literals and trailing comments to reduce false positives."""
    result = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
    result = re.sub(r"'(?:[^'\\]|\\.)*'", "''", result)
    result = re.sub(r"`(?:[^`\\]|\\.)*`", "``", result)
    result = re.sub(r"//.*$", "", result)
    result = re.sub(r"#.*$", "", result)
    return result


def _count_decision_points(line: str, ext: str) -> int:
    """Count cyclomatic complexity decision points on a single line."""
    stripped = _strip_strings_and_comments(line)
    count = 0
    for pattern in DECISION_PATTERNS:
        count += len(pattern.findall(stripped))
    count += len(LOGICAL_OP_PATTERN.findall(stripped))
    if ext == ".py":
        count += len(PYTHON_LOGICAL_PATTERN.findall(stripped))
    count += len(NULL_COALESCE_PATTERN.findall(stripped))
    # Ternary ? — remove ?? first to avoid double-counting
    cleaned = NULL_COALESCE_PATTERN.sub("", stripped)
    count += len(TERNARY_PATTERN.findall(cleaned))
    return count


def _extract_functions_indent(lines: List[str], ext: str) -> List[Tuple[str, int, List[str]]]:
    """Extract functions from indentation-based languages (Python)."""
    functions: List[Tuple[str, int, List[str]]] = []
    i = 0
    while i < len(lines):
        func_name = _match_function(lines[i])
        if func_name is not None:
            func_indent = _indent_level(lines[i])
            body_lines: List[str] = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip() == "":
                    body_lines.append(lines[j])
                    j += 1
                elif _indent_level(lines[j]) > func_indent:
                    body_lines.append(lines[j])
                    j += 1
                else:
                    break
            functions.append((func_name, i + 1, body_lines))
            i = j
        else:
            i += 1
    return functions


def _extract_functions_brace(lines: List[str], ext: str) -> List[Tuple[str, int, List[str]]]:
    """Extract functions from brace-based languages (JS, TS, Java, Go, etc.)."""
    functions: List[Tuple[str, int, List[str]]] = []
    i = 0
    while i < len(lines):
        func_name = _match_function(lines[i])
        if func_name is not None:
            brace_depth, found_open = 0, False
            body_lines: List[str] = []
            j = i
            while j < len(lines):
                current = _strip_strings_and_comments(lines[j])
                for ch in current:
                    if ch == "{":
                        brace_depth += 1
                        found_open = True
                    elif ch == "}":
                        brace_depth -= 1
                if j > i:
                    body_lines.append(lines[j])
                if found_open and brace_depth == 0:
                    break
                j += 1
            functions.append((func_name, i + 1, body_lines))
            i = j + 1
        else:
            i += 1
    return functions


def _extract_functions_simple(lines: List[str], ext: str) -> List[Tuple[str, int, List[str]]]:
    """Fallback: collect lines between consecutive function declarations."""
    functions: List[Tuple[str, int, List[str]]] = []
    current_func: Optional[str] = None
    current_line: int = 0
    current_body: List[str] = []
    for i, line in enumerate(lines):
        func_name = _match_function(line)
        if func_name is not None:
            if current_func is not None:
                functions.append((current_func, current_line, current_body))
            current_func, current_line, current_body = func_name, i + 1, []
        elif current_func is not None:
            current_body.append(line)
    if current_func is not None:
        functions.append((current_func, current_line, current_body))
    return functions


def _rate_complexity(complexity: int) -> str:
    """Return a human-readable rating for a complexity score."""
    if complexity <= 5:
        return "low"
    elif complexity <= 10:
        return "moderate"
    elif complexity <= 20:
        return "high"
    return "very_high"


def analyze_file(filepath: str, ext: str) -> Optional[List[Dict[str, Any]]]:
    """Analyze a single source file and return per-function complexity data."""
    try:
        if os.path.getsize(filepath) > MAX_FILE_SIZE:
            return None
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (PermissionError, OSError, IOError):
        return None

    if ext in INDENT_LANGUAGES:
        functions = _extract_functions_indent(lines, ext)
    elif ext in BRACE_LANGUAGES:
        functions = _extract_functions_brace(lines, ext)
    else:
        functions = _extract_functions_simple(lines, ext)

    results: List[Dict[str, Any]] = []
    for func_name, line_no, body_lines in functions:
        complexity = 1  # base complexity
        for body_line in body_lines:
            complexity += _count_decision_points(body_line, ext)
        results.append({
            "function": func_name,
            "line": line_no,
            "complexity": complexity,
            "rating": _rate_complexity(complexity),
        })
    return results


def compute_summary(function_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate statistics from per-function entries."""
    total = len(function_entries)
    if total == 0:
        return {
            "total_functions": 0,
            "avg_complexity": 0.0,
            "functions_over_10": 0,
            "functions_over_20": 0,
            "highest": {"file": "", "function": "", "complexity": 0},
        }

    avg = round(sum(e["complexity"] for e in function_entries) / total, 1)
    highest = max(function_entries, key=lambda e: e["complexity"])
    return {
        "total_functions": total,
        "avg_complexity": avg,
        "functions_over_10": sum(1 for e in function_entries if e["complexity"] > 10),
        "functions_over_20": sum(1 for e in function_entries if e["complexity"] > 20),
        "highest": {
            "file": highest["file"],
            "function": highest["function"],
            "complexity": highest["complexity"],
        },
    }


def main() -> None:
    if len(sys.argv) < 2:
        json.dump(
            {"error": "Usage: python3 complexity_scorer.py /path/to/project"},
            sys.stdout, indent=2,
        )
        sys.exit(1)

    target_dir = os.path.realpath(sys.argv[1])
    if not os.path.isdir(target_dir):
        json.dump(
            {"error": f"Directory not found: {target_dir}"},
            sys.stdout, indent=2,
        )
        sys.exit(1)

    # Collect and analyze files
    file_paths = collect_files(target_dir)
    root = os.path.abspath(target_dir)
    function_entries: List[Dict[str, Any]] = []

    for rel_path in file_paths:
        full_path = os.path.join(root, rel_path)
        ext = os.path.splitext(rel_path)[1].lower()
        results = analyze_file(full_path, ext)
        if results is not None:
            for entry in results:
                entry["file"] = rel_path
                function_entries.append(entry)

    output = {
        "functions": function_entries,
        "summary": compute_summary(function_entries),
    }
    json.dump(output, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
