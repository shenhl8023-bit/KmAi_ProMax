# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class PythonRuntimeDiagnosticsTests(unittest.TestCase):
    class _FakeServer(object):
        server_address = ("127.0.0.1", 9095)

    def _make_health_handler(self, http_api):
        handler = object.__new__(http_api.AgentRequestHandler)
        handler.path = "/api/health"
        handler.command = "GET"
        handler.server = self._FakeServer()
        handler.headers = {
            "Origin": "http://127.0.0.1:9095",
            "X-KmAI-Token": http_api.API_AUTH_TOKEN,
        }
        handler.sent_json = []
        handler._send_json = lambda status, data: handler.sent_json.append((status, data))
        return handler

    def test_start_script_requires_python_310_and_exports_skill_python(self):
        script_path = os.path.join(SERVER_ROOT, "start_agent.bat")
        with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            script = fp.read()

        self.assertIn("PYTHON_MIN_MAJOR=3", script)
        self.assertIn("PYTHON_MIN_MINOR=10", script)
        self.assertIn("resolve_python_runtime.ps1", script)
        self.assertIn("KMAI_PYTHON_EXE=%PYTHON_EXE%", script)
        self.assertIn("KMAI_SKILL_PYTHON=%PYTHON_EXE%", script)
        self.assertNotIn("Python3.6_win32\\python.exe", script)

        resolver_path = os.path.join(SERVER_ROOT, "resolve_python_runtime.ps1")
        with open(resolver_path, "r", encoding="utf-8-sig") as fp:
            resolver = fp.read()
        self.assertIn("Python3.10_win32", resolver)
        self.assertNotIn("Python3.6_win32", resolver)

    def test_health_includes_python_and_skill_runtime_diagnostics(self):
        from backend import http_api

        handler = self._make_health_handler(http_api)

        handler.do_GET()

        status, payload = handler.sent_json[0]
        self.assertEqual(200, status)
        self.assertIn("python", payload)
        self.assertEqual(sys.executable, payload["python"].get("executable"))
        self.assertIn("version", payload["python"])
        self.assertIn("version_info", payload["python"])

        self.assertIn("skills", payload)
        skill_diag = payload["skills"]
        self.assertIn("python_ok", skill_diag)
        self.assertIn("tools", skill_diag)
        self.assertEqual(
            "3.10",
            skill_diag["tools"]["process_route_generate"].get("python_min_version"),
        )
        self.assertEqual(
            "3.10",
            skill_diag["tools"]["technical_requirements_generate"].get("python_min_version"),
        )

    def test_health_includes_km3dmps_exe_runtime_diagnostics(self):
        from backend import http_api

        handler = self._make_health_handler(http_api)

        handler.do_GET()

        status, payload = handler.sent_json[0]
        self.assertEqual(200, status)
        self.assertIn("km3dmps", payload)
        km3dmps = payload["km3dmps"]
        self.assertIn("running", km3dmps)
        self.assertIn("processes", km3dmps)
        self.assertIn("expected_exe_path", km3dmps)
        self.assertIn("expected_exe_exists", km3dmps)
        self.assertIn("expected_exe_last_write_time", km3dmps)
        self.assertTrue(km3dmps["expected_exe_path"].lower().endswith("km3dmps.exe"))

    def test_health_reports_unavailable_for_platform_pipe_without_availability_probe(self):
        from backend import http_api
        handler = self._make_health_handler(http_api)
        with patch.object(http_api.AGENT, "pipe", object()):
            handler.do_GET()
        status, payload = handler.sent_json[0]
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIs(payload["pipe_available"], False)

    def test_check_3dmps_status_includes_km3dmps_runtime_diagnostics(self):
        from backend import http_api

        result = http_api.AGENT.tool("check_3dmps_status", {})

        self.assertIn("km3dmps", result)
        km3dmps = result["km3dmps"]
        self.assertIn("running", km3dmps)
        self.assertIn("processes", km3dmps)
        self.assertIn("expected_exe_path", km3dmps)
        self.assertIn("expected_exe_last_write_time", km3dmps)

    def test_function_not_found_reply_mentions_exe_diagnostics_and_restart(self):
        from backend import http_api

        reply = http_api.AGENT._tool_error_reply(
            "main.bof_root_params.get",
            {
                "status": "error",
                "error_code": "FUNCTION_NOT_FOUND",
                "message": "Function not found: main.bof_root_params.get",
            },
        )

        self.assertIn("Km3dmps.exe", reply)
        self.assertIn("时间戳", reply)
        self.assertIn("重启", reply)


if __name__ == "__main__":
    unittest.main()
