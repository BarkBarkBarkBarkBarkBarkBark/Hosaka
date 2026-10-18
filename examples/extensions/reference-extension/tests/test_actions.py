import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reference_actions", ROOT / "main.py")
assert spec is not None and spec.loader is not None
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)


class LocalContext:
    """Test fixture only: not an OS sandbox or production host capability."""

    def __init__(self, root):
        self.root = Path(root)
        self.events = []

    def target(self, name):
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root.resolve()) or Path(name).name != name:
            raise PermissionError("Only local data filenames are accepted.")
        return target

    def read_data(self, name):
        target = self.target(name)
        return target.read_text() if target.exists() else None

    def write_data(self, name, value):
        self.target(name).write_text(value)

    def delete_data(self, name):
        self.target(name).unlink(missing_ok=True)

    def log(self, event, metadata):
        self.events.append({"event": event, **metadata})


class ReferenceTests(unittest.TestCase):
    def test_echo_and_structured_error(self):
        with tempfile.TemporaryDirectory() as directory:
            context = LocalContext(directory)
            self.assertEqual(actions.run("echo", {"message": "Hello"}, context)["message"], "Hello")
            result = actions.run("fail", {}, context)
            self.assertFalse(result["success"])
            self.assertIn("Intentional", result["error"])
            self.assertEqual(len(context.events), 2)
            json.dumps(result)

    def test_persistence_across_contexts_and_explicit_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            actions.run("save", {"message": "kept value"}, LocalContext(directory))
            result = actions.run("load", {}, LocalContext(directory))
            self.assertEqual(result["message"], "kept value")
            actions.run("delete", {}, LocalContext(directory))
            self.assertEqual(actions.run("load", {}, LocalContext(directory))["message"], "")

    def test_invalid_input_and_unknown_action(self):
        with tempfile.TemporaryDirectory() as directory:
            context = LocalContext(directory)
            for action, params in (("echo", {"message": 1}), ("unknown", {}), ("load", {"unexpected": True})):
                with self.assertRaises(ValueError):
                    actions.run(action, params, context)

    def test_context_rejects_escaping_data_names(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PermissionError):
                LocalContext(directory).write_data("../escape", "no")

    def test_package_contract(self):
        from jsonschema import Draft202012Validator
        from hosaka.extensions.manifest import validate_package

        package = validate_package(ROOT)
        self.assertEqual(set(package.manifest.actions), {"echo", "save", "load", "delete", "fail"})
        with tempfile.TemporaryDirectory() as directory:
            context = LocalContext(directory)
            for name, action in package.manifest.actions.items():
                params = {"message": "contract proof"} if name in {"echo", "save"} else {}
                input_schema = json.loads((ROOT / action.input_schema).read_text())
                output_schema = json.loads((ROOT / action.output_schema).read_text())
                Draft202012Validator(input_schema).validate(params)
                Draft202012Validator(output_schema).validate(actions.run(name, params, context))


if __name__ == "__main__":
    unittest.main()
