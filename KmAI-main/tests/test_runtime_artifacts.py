# -*- coding: utf-8 -*-
from __future__ import print_function

import importlib
import os
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)


class RuntimeArtifactTests(unittest.TestCase):
    def test_audit_log_defaults_to_user_runtime_dir(self):
        old_runtime_dir = os.environ.get("KMAI_RUNTIME_DIR")
        try:
            with tempfile.TemporaryDirectory() as runtime_dir:
                os.environ["KMAI_RUNTIME_DIR"] = runtime_dir

                from backend import audit
                importlib.reload(audit)

                expected = os.path.join(runtime_dir, "logs", "agent_server.audit.log")
                self.assertEqual(
                    os.path.abspath(expected),
                    os.path.abspath(audit.DEFAULT_LOG_PATH),
                )
                self.assertFalse(
                    os.path.abspath(audit.DEFAULT_LOG_PATH).startswith(
                        os.path.abspath(SERVER_ROOT) + os.sep
                    )
                )
        finally:
            if old_runtime_dir is None:
                os.environ.pop("KMAI_RUNTIME_DIR", None)
            else:
                os.environ["KMAI_RUNTIME_DIR"] = old_runtime_dir
            from backend import audit
            importlib.reload(audit)

    def test_start_script_redirects_logs_to_runtime_dir_and_disables_bytecode(self):
        script_path = os.path.join(SERVER_ROOT, "start_agent.bat")
        with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            script = fp.read()

        self.assertIn("KMAI_RUNTIME_DIR", script)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", script)
        self.assertIn("agent_server.out.log", script)
        self.assertIn("agent_server.err.log", script)
        self.assertNotIn("RedirectStandardOutput '%BASE_DIR%agent_server.out.log'", script)
        self.assertNotIn("RedirectStandardError '%BASE_DIR%agent_server.err.log'", script)

    def test_start_script_waits_for_tcp_listener_before_reporting_success(self):
        script_path = os.path.join(SERVER_ROOT, "start_agent.bat")
        with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            script = fp.read()

        self.assertIn("KMAI_HEALTH_URL=%AGENT_HOST%:%AGENT_PORT%", script)
        self.assertIn(":wait_for_health", script)
        self.assertIn("New-Object Net.Sockets.TcpClient", script)
        self.assertIn("[ERROR] Server listener did not become ready", script)
        self.assertNotIn("Server start command issued", script)

    def test_start_script_treats_existing_kmai_agent_as_already_running(self):
        script_path = os.path.join(SERVER_ROOT, "start_agent.bat")
        with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            script = fp.read()

        self.assertIn("KMAI_STARTUP_PING_URL=http://%AGENT_HOST%:%AGENT_PORT%/api/startup-ping", script)
        self.assertIn("[OK] Server already running at http://%KMAI_HEALTH_URL%/", script)
        self.assertIn("exit /b 0", script)
        self.assertIn("[ERROR] Port %AGENT_PORT% is already in use by another process.", script)

    def test_run_test_scripts_disable_bytecode_cache(self):
        for script_name in ("run_tests.bat", "run_tests.ps1"):
            script_path = os.path.join(ROOT, script_name)
            with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
                script = fp.read()

            self.assertIn("-B", script, script_name)
            self.assertIn("unittest discover", script, script_name)
            self.assertIn("KmMpsMcpServer", script, script_name)
            if script_name.endswith(".ps1"):
                self.assertIn("Push-Location", script, script_name)
                self.assertIn("Pop-Location", script, script_name)
            else:
                self.assertIn("pushd", script.lower(), script_name)
                self.assertIn("popd", script.lower(), script_name)

    def test_root_entrypoint_disables_bytecode_before_backend_import(self):
        entry_path = os.path.join(SERVER_ROOT, "agent_server.py")
        with open(entry_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            entry = fp.read()

        bytecode_pos = entry.index("sys.dont_write_bytecode = True")
        import_pos = entry.index("from backend.agent_server import main")
        self.assertLess(bytecode_pos, import_pos)


if __name__ == "__main__":
    unittest.main()
