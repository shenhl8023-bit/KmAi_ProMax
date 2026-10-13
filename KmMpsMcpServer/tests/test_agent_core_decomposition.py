import ast
import inspect
import unittest
from pathlib import Path

from backend import agent_core


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = Path(__file__).resolve().parent / "miniagent_method_contract.txt"
EXPECTED_MODULES = (
    "session_store.py",
    "llm_service.py",
    "tool_dispatcher.py",
    "bof_formatter.py",
    "autoidentify_service.py",
    "group_template_service.py",
    "chat_service.py",
)


class AgentCoreDecompositionTests(unittest.TestCase):
    def test_expected_service_modules_exist(self):
        missing = [
            name for name in EXPECTED_MODULES
            if not (ROOT / "backend" / name).is_file()
        ]
        self.assertEqual([], missing)

    def test_miniagent_preserves_method_descriptor_contract(self):
        mini_agent = agent_core.MiniAgent
        rows = [
            line.split("|", 1)
            for line in CONTRACT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(101, len(rows))
        for name, expected_kind in rows:
            self.assertTrue(hasattr(mini_agent, name), name)
            self.assertTrue(callable(getattr(mini_agent, name)), name)
            descriptor = inspect.getattr_static(mini_agent, name)
            if expected_kind == "staticmethod":
                self.assertIsInstance(descriptor, staticmethod, name)
            elif expected_kind == "classmethod":
                self.assertIsInstance(descriptor, classmethod, name)
            else:
                self.assertTrue(inspect.isfunction(descriptor), name)

    def test_agent_core_keeps_session_store_compatibility_alias(self):
        from backend.session_store import SessionStore

        self.assertIs(SessionStore, agent_core._SessionStore)
        self.assertEqual("backend.agent_core", agent_core.MiniAgent.__module__)

    def test_miniagent_is_only_a_thin_composition_entrypoint(self):
        class_source = inspect.getsource(agent_core.MiniAgent)
        class_tree = ast.parse(class_source)
        class_node = next(
            node for node in class_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MiniAgent"
        )
        direct_methods = [
            node.name for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        agent_core_lines = len(
            (ROOT / "backend" / "agent_core.py")
            .read_text(encoding="utf-8")
            .splitlines()
        )

        self.assertEqual(["__init__"], direct_methods)
        self.assertLessEqual(agent_core_lines, 120)


if __name__ == "__main__":
    unittest.main()
