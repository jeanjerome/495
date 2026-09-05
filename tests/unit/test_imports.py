import ast
import unittest
from pathlib import Path


class ImportBoundariesTest(unittest.TestCase):
    def test_domain_has_no_io_dynamic_or_project_dependencies(self):
        forbidden = {
            "asyncio", "ctypes", "dbm", "fcntl", "fileinput", "ftplib", "glob",
            "http", "importlib", "io", "mmap", "multiprocessing", "os", "pathlib",
            "pickle", "selectors", "shelve", "shutil", "signal", "smtplib", "socket",
            "socketserver", "sqlite3", "ssl", "subprocess", "tempfile", "urllib",
            "webbrowser", "xmlrpc",
        }
        forbidden_calls = {"open", "eval", "exec", "compile", "__import__"}
        roots = (
            Path("src/domain"),
            Path("src/validation"),
            Path("src/policy"),
            Path("src/csap"),
        )
        for path in sorted(path for root in roots for path in root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden, str(path))
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden, str(path))
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden_calls, str(path))

    def test_internal_imports_follow_the_dependency_levels(self):
        levels = {
            "vocabulary": 0,
            "outcomes": 1,
            "references": 2,
            "revisions": 3,
            "sealing": 3,
            "links": 3,
            "invalidation": 3,
            "phases": 3,
            "attempts": 3,
            "state": 4,
            "commands": 5,
        }
        for module, level in levels.items():
            path = Path("src/domain") / f"{module}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1:
                    dependency = (node.module or "").split(".")[0]
                    self.assertLess(levels[dependency], level, f"{module} -> {dependency}")

    def test_decision_packages_only_depend_downward(self):
        allowed = {
            "validation": {"domain"},
            "policy": {"domain", "validation"},
        }
        forbidden_project = {"application", "ports", "infrastructure"}
        for package in ("validation", "policy"):
            for path in sorted((Path("src") / package).glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                        imported = node.module.split(".")[0]
                        self.assertNotIn(imported, forbidden_project, str(path))
                        if imported in {"domain", "validation", "policy"}:
                            self.assertIn(imported, allowed[package], str(path))

    def test_pure_packages_do_not_import_persistence(self):
        for package in ("domain", "validation", "policy", "persistence"):
            for path in sorted((Path("src") / package).glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        self.assertNotEqual(node.module.split(".")[0], "persistence", str(path))

    def test_lower_packages_do_not_import_csap(self):
        for package in ("domain", "validation", "policy", "persistence"):
            for path in sorted((Path("src") / package).glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        self.assertNotEqual(node.module.split(".")[0], "csap", str(path))
