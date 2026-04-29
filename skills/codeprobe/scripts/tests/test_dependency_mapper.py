"""Regression tests for dependency_mapper.py.

Runs the script via subprocess so the public entry point is exercised end-to-end.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest


SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dependency_mapper.py",
)


def run_mapper(target_dir: str) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH, target_dir],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def write(path: str, content: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class DependencyMapperTests(unittest.TestCase):
    def test_sibling_python_imports_form_cycle(self):
        """Two flat-layout siblings importing each other are captured."""
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, "alpha.py"), "from beta import b\n")
            write(os.path.join(tmp, "beta.py"), "from alpha import a\n")

            output = run_mapper(tmp)
            graph = output["graph"]

            self.assertIn("alpha.py", graph, f"graph missing alpha.py: {graph}")
            self.assertIn("beta.py", graph, f"graph missing beta.py: {graph}")
            self.assertIn("beta.py", graph["alpha.py"])
            self.assertIn("alpha.py", graph["beta.py"])
            self.assertEqual(len(output["circular_dependencies"]), 1)

    def test_pep328_relative_imports_resolve(self):
        """Single- and double-dot relative imports walk the importer's dir."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = os.path.join(tmp, "pkg")
            sub = os.path.join(pkg, "sub")
            write(os.path.join(pkg, "__init__.py"))
            write(os.path.join(sub, "__init__.py"))
            write(os.path.join(pkg, "uncle.py"), "x = 1\n")
            write(os.path.join(pkg, "sibling.py"), "x = 1\n")
            write(
                os.path.join(sub, "child.py"),
                "from ..uncle import x\n"
                "from ..sibling import x as y\n",
            )

            output = run_mapper(tmp)
            graph = output["graph"]
            child_key = "pkg/sub/child.py"
            self.assertIn(child_key, graph, f"graph: {graph}")
            self.assertIn("pkg/uncle.py", graph[child_key])
            self.assertIn("pkg/sibling.py", graph[child_key])


if __name__ == "__main__":
    unittest.main()
