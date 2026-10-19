# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from skills.runner import SkillRunner
import skills.runner as runner_module
import skills


class SkillRuntimeResolutionTests(unittest.TestCase):
    def _runner(self, command="node", **extra):
        config = {
            "name": "test",
            "tool_name": "test_tool",
            "command": command,
            "args": ["script.js"] if command == "node" else ["script.py"],
        }
        config.update(extra)
        return SkillRunner(config)

    def test_win7_node_env_executable_has_priority_over_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit = os.path.join(temp_dir, "node12.exe")
            with open(explicit, "wb") as stream:
                stream.write(b"fixture")
            with mock.patch.dict(
                os.environ,
                {"KMAI_WIN7_COMPAT": "1", "KMAI_NODE_EXE": explicit},
                clear=False,
            ):
                with mock.patch.object(runner_module.shutil, "which", return_value="path-node"):
                    command = self._runner()._build_cmdline({})
            self.assertEqual(explicit, command[0])

    def test_node_falls_back_to_package_runtime_before_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = os.path.join(temp_dir, "package")
            skills_dir = os.path.join(package_root, "KmMpsMcpServer", "skills")
            runtime_dir = os.path.join(package_root, "runtime")
            os.makedirs(skills_dir)
            os.makedirs(runtime_dir)
            package_node = os.path.join(runtime_dir, "node.exe")
            with open(package_node, "wb") as stream:
                stream.write(b"fixture")
            state_dir = os.path.join(temp_dir, "state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "node.exe"), "wb") as stream:
                stream.write(b"wrong")
            fake_runner_file = os.path.join(skills_dir, "runner.py")
            with mock.patch.object(runner_module, "__file__", fake_runner_file):
                with mock.patch.dict(
                    os.environ,
                    {
                        "KMAI_WIN7_COMPAT": "1",
                        "KMAI_RUNTIME_DIR": state_dir,
                    },
                    clear=False,
                ):
                    with mock.patch.object(runner_module.shutil, "which", return_value="path-node"):
                        command = self._runner()._build_cmdline({})
            self.assertEqual(package_node, command[0])
            self.assertNotEqual(state_dir, os.path.dirname(os.path.dirname(command[0])))

    def test_win7_node_does_not_fall_back_to_path_when_package_runtime_is_missing(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_runner_file = os.path.join(temp_dir, "KmMpsMcpServer", "skills", "runner.py")
            with mock.patch.object(runner_module, "__file__", fake_runner_file):
                with mock.patch.dict(
                    os.environ,
                    {"KMAI_WIN7_COMPAT": "1", "KMAI_NODE_EXE": ""},
                    clear=False,
                ):
                    with mock.patch.object(runner_module.shutil, "which", return_value="path-node"):
                        with self.assertRaises(runner_module.RuntimeResolutionError) as caught:
                            runner._resolve_node_command()
            self.assertEqual("NODE_NOT_FOUND", caught.exception.error_code)

    def test_win7_python_profile_accepts_38_but_default_keeps_310(self):
        action = {
            "python_min_version": "3.10",
            "python_min_version_win7": "3.8",
        }
        runner = self._runner("python-auto", args=["script.py"], **action)
        with mock.patch.dict(os.environ, {"KMAI_WIN7_COMPAT": "1"}, clear=False):
            self.assertEqual((3, 8), runner._minimum_python_version())
        with mock.patch.dict(os.environ, {"KMAI_WIN7_COMPAT": "0"}, clear=False):
            self.assertEqual((3, 10), runner._minimum_python_version())

    def test_win7_python_does_not_fall_back_to_system_launcher_or_path(self):
        runner = self._runner("python-auto", args=["script.py"])
        with mock.patch.dict(
            os.environ,
            {"KMAI_WIN7_COMPAT": "1", "KMAI_SKILL_PYTHON": "", "KMAI_PYTHON_EXE": ""},
            clear=False,
        ):
            with mock.patch.object(runner, "_probe_python_version", return_value=None):
                with mock.patch.object(runner_module, "_load_python_launcher_versions") as launcher_versions:
                    with self.assertRaisesRegex(RuntimeError, "Win7 Skill Python"):
                        runner._resolve_python_command()
                    launcher_versions.assert_not_called()

    def test_win7_python_rejects_invalid_explicit_runtime_without_fallback(self):
        runner = self._runner("python-auto", args=["script.py"])
        with mock.patch.dict(
            os.environ,
            {"KMAI_WIN7_COMPAT": "1", "KMAI_SKILL_PYTHON": "bad-python.exe"},
            clear=False,
        ):
            with mock.patch.object(runner, "_probe_python_version", return_value=None):
                with mock.patch.object(runner_module, "_load_python_launcher_versions") as launcher_versions:
                    with self.assertRaisesRegex(RuntimeError, "Win7 Skill Python"):
                        runner._resolve_python_command()
                    launcher_versions.assert_not_called()

    def test_win7_python_diagnostic_has_stable_error_code(self):
        runner = self._runner("python-auto", args=["script.py"])
        with mock.patch.dict(
            os.environ,
            {"KMAI_WIN7_COMPAT": "1", "KMAI_SKILL_PYTHON": "", "KMAI_PYTHON_EXE": ""},
            clear=False,
        ):
            with mock.patch.object(runner, "_probe_python_version", return_value=None):
                result = skills._diagnose_runner_runtime(runner)
        self.assertFalse(result["ok"])
        self.assertEqual("PYTHON_NOT_FOUND", result.get("error_code"))

    def test_missing_win7_node_reports_structured_error(self):
        runner = self._runner()
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(runner_module, "__file__", os.path.join(temp_dir, "runner.py")):
                with mock.patch.dict(
                    os.environ,
                    {"KMAI_WIN7_COMPAT": "1", "KMAI_NODE_EXE": "missing-node"},
                    clear=False,
                ):
                    with mock.patch.object(runner_module.shutil, "which", return_value=None):
                        result = skills._diagnose_runner_runtime(runner)
        self.assertFalse(result["ok"])
        self.assertEqual("NODE_NOT_FOUND", result.get("error_code"))
        self.assertEqual("", result.get("resolved_command"))
        self.assertNotIn("KMAI_NODE_EXE", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
