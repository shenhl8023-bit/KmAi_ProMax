# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import unittest
from unittest import mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

import skills


class SkillRuntimeDiagnosticsTests(unittest.TestCase):
    class _Runner(object):
        def __init__(self, command):
            self.command = command
            self.python_min_version = None

        def _resolve_python_command(self):
            return [sys.executable]

        def _probe_python_version(self, command):
            return sys.version_info[:2]

    @staticmethod
    def _process(stdout=b"", stderr=b"", returncode=0):
        process = mock.Mock()
        process.communicate.return_value = (stdout, stderr)
        process.returncode = returncode
        return process

    def test_missing_node_reports_node_not_found(self):
        with mock.patch.object(skills.shutil, "which", return_value=None):
            result = skills._diagnose_runner_runtime(self._Runner("node"))

        self.assertFalse(result["ok"])
        self.assertEqual("NODE_NOT_FOUND", result.get("error_code"))
        self.assertEqual("", result.get("resolved_command"))
        self.assertEqual("", result.get("resolved_version"))

    def test_existing_node_reports_absolute_path_and_version(self):
        node_path = os.path.abspath(os.path.join(ROOT, "fake-runtime", "node.exe"))
        process = self._process(stdout=b"v24.13.0\r\n")

        with mock.patch.object(skills.shutil, "which", return_value=node_path):
            with mock.patch.object(skills.subprocess, "Popen", return_value=process) as popen:
                result = skills._diagnose_runner_runtime(self._Runner("node"))

        self.assertTrue(result["ok"])
        self.assertEqual(node_path, result.get("resolved_command"))
        self.assertEqual("24.13.0", result.get("resolved_version"))
        popen.assert_called_once_with(
            [node_path, "--version"],
            stdout=skills.subprocess.PIPE,
            stderr=skills.subprocess.PIPE,
            creationflags=getattr(skills.subprocess, "CREATE_NO_WINDOW", 0),
        )
        process.communicate.assert_called_once_with(timeout=10.0)

    def test_missing_generic_runtime_is_not_reported_healthy(self):
        with mock.patch.object(skills.shutil, "which", return_value=None):
            result = skills._diagnose_runner_runtime(
                self._Runner("definitely-not-installed-kmai-runtime")
            )

        self.assertFalse(result["ok"])
        self.assertEqual("RUNTIME_NOT_FOUND", result.get("error_code"))

    def test_runtime_diagnostics_aggregates_all_runner_health(self):
        runners = {
            "node_tool": self._Runner("node"),
            "python_tool": self._Runner("python-auto"),
        }

        def diagnose(runner):
            return {"command": runner.command, "ok": runner.command != "node"}

        with mock.patch.object(skills, "SKILL_RUNNERS", runners):
            with mock.patch.object(skills, "_diagnose_runner_runtime", side_effect=diagnose):
                result = skills.get_runtime_diagnostics()

        self.assertIn("runtimes_ok", result)
        self.assertFalse(result["runtimes_ok"])
        self.assertTrue(result.get("python_ok"))


if __name__ == "__main__":
    unittest.main()

