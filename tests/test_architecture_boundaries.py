import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_MODULES = ROOT / "xiaoxue_api" / "modules"


class BackendArchitectureBoundaryTests(unittest.TestCase):
    def test_main_is_only_a_compatibility_composition_entry(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertLessEqual(len(source.splitlines()), 20)
        self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body))

    def test_active_modules_have_presentation_service_and_data_layers(self):
        for module_name in (
            "lineup", "market_notes", "team_data", "daily_content",
            "profiles", "tk_knowledge", "fundamentals", "analyst", "platform", "weread_bridge",
            "pre_match", "legacy_trades",
            "current_event",
        ):
            module_dir = BACKEND_MODULES / module_name
            with self.subTest(module=module_name):
                self.assertTrue((module_dir / "presentation.py").is_file())
                self.assertTrue((module_dir / "service.py").is_file())
                self.assertTrue((module_dir / "repository.py").is_file())
                self.assertTrue((module_dir / "public.py").is_file())

    def test_backend_modules_never_import_the_application_shell(self):
        for path in BACKEND_MODULES.glob("**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = _imports(tree)
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("main", imported)

    def test_cross_module_imports_only_target_public_interfaces(self):
        for path in BACKEND_MODULES.glob("**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in _imports(tree):
                if not imported.startswith("xiaoxue_api.modules."):
                    continue
                target = imported.split(".")
                source_module = path.relative_to(BACKEND_MODULES).parts[0]
                target_module = target[2] if len(target) > 2 else ""
                if target_module == source_module:
                    continue
                with self.subTest(path=path.relative_to(ROOT), imported=imported):
                    self.assertTrue(imported.endswith(".public"))

    def test_backend_layers_only_depend_downward(self):
        for module_dir in BACKEND_MODULES.iterdir():
            if not module_dir.is_dir():
                continue
            presentation = module_dir / "presentation.py"
            service = module_dir / "service.py"
            repository = module_dir / "repository.py"
            if presentation.exists():
                imports = _imports(ast.parse(presentation.read_text(encoding="utf-8")))
                with self.subTest(module=module_dir.name, layer="presentation"):
                    self.assertFalse(any(name.endswith(".repository") for name in imports))
                    self.assertNotIn("sqlite3", imports)
            if service.exists():
                imports = _imports(ast.parse(service.read_text(encoding="utf-8")))
                with self.subTest(module=module_dir.name, layer="service"):
                    self.assertFalse(any(name.endswith(".presentation") or name.endswith(".router") for name in imports))
                    self.assertNotIn("fastapi", imports)
            if repository.exists():
                imports = _imports(ast.parse(repository.read_text(encoding="utf-8")))
                with self.subTest(module=module_dir.name, layer="repository"):
                    self.assertFalse(any(name.endswith(".service") or name.endswith(".presentation") for name in imports))


def _imports(tree: ast.AST) -> set[str]:
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


if __name__ == "__main__":
    unittest.main()
