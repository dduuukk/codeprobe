"""Tests for the unified METHOD_PATTERNS contract in _common.py.

Each pattern must match its language's function/method declaration and
capture the identifier under the named group "name".
"""

import os
import sys
import unittest


SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from _common import METHOD_PATTERNS  # noqa: E402
from complexity_scorer import _match_function  # noqa: E402
from file_stats import count_methods  # noqa: E402


# (description, source_line, expected_captured_name)
MATCH_CASES = [
    ("python def", "def hello():", "hello"),
    ("python def indented", "    def hello():", "hello"),
    ("python def underscore", "def _private(x, y):", "_private"),
    ("js named function", "function foo() {", "foo"),
    ("js exported async function",
     "export async function fetchUser() {", "fetchUser"),
    ("php class method", "    public function getUser() {", "getUser"),
    ("php static method",
     "    private static function helper() {", "helper"),
    ("java method",
     "    public static int sum(int a, int b) {", "sum"),
    ("rust fn", "fn main() {", "main"),
    ("rust pub async fn",
     "pub async fn handle_request() {", "handle_request"),
    ("go func", "func main() {", "main"),
    ("go method with receiver",
     "func (s *Server) Handle() {", "Handle"),
    ("go method with pointer receiver",
     "func (s *Server) handle() error {", "handle"),
    ("arrow function const",
     "const myHandler = (req, res) => {", "myHandler"),
    ("arrow async function let",
     "let fetchData = async () => {", "fetchData"),
]

# Lines that must NOT match any pattern.
NON_MATCH_CASES = [
    "x = 1",
    "if foo:",
    "return x",
    "function()",       # call, not declaration
    "func()",           # Go call, not declaration
    "# def hidden():",  # commented-out Python
    "// function bar()",  # commented-out JS
    "    items = [1, 2, 3]",
]


class MethodPatternsTest(unittest.TestCase):
    def test_each_language_captures_name(self):
        for desc, line, expected in MATCH_CASES:
            with self.subTest(case=desc):
                hit = None
                for pattern in METHOD_PATTERNS:
                    m = pattern.match(line)
                    if m:
                        hit = m
                        break
                self.assertIsNotNone(
                    hit, f"{desc}: no METHOD_PATTERN matched {line!r}",
                )
                self.assertEqual(
                    hit.group("name"), expected,
                    f"{desc}: expected name={expected!r}, got {hit.group('name')!r}",
                )

    def test_non_declarations_do_not_match(self):
        for line in NON_MATCH_CASES:
            with self.subTest(line=line):
                for pattern in METHOD_PATTERNS:
                    self.assertIsNone(
                        pattern.match(line),
                        f"unexpected match on {line!r} by {pattern.pattern!r}",
                    )

    def test_every_pattern_defines_name_group(self):
        """Contract: every pattern must capture under 'name' so consumers
        can rely on m.group('name') without checking which pattern matched."""
        for pattern in METHOD_PATTERNS:
            self.assertIn(
                "name", pattern.groupindex,
                f"pattern missing 'name' group: {pattern.pattern!r}",
            )


class MatchFunctionTest(unittest.TestCase):
    """complexity_scorer._match_function consumes METHOD_PATTERNS via
    m.group('name') — verify it agrees with the pattern matcher."""

    def test_returns_captured_name(self):
        for desc, line, expected in MATCH_CASES:
            with self.subTest(case=desc):
                self.assertEqual(_match_function(line), expected)

    def test_returns_none_for_non_declarations(self):
        for line in NON_MATCH_CASES:
            with self.subTest(line=line):
                self.assertIsNone(_match_function(line))


class CountMethodsTest(unittest.TestCase):
    """file_stats.count_methods uses METHOD_PATTERNS in boolean-match mode —
    adding the named group must not change its output."""

    def test_returns_one_on_match(self):
        for desc, line, _ in MATCH_CASES:
            with self.subTest(case=desc):
                self.assertEqual(count_methods(line), 1)

    def test_returns_zero_on_non_declaration(self):
        for line in NON_MATCH_CASES:
            with self.subTest(line=line):
                self.assertEqual(count_methods(line), 0)


if __name__ == "__main__":
    unittest.main()
