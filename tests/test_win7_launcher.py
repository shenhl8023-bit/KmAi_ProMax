# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "deploy" / "win7-compat" / "launcher.py"
DEPLOY = LAUNCHER.parent

sys.path.insert(0, str(DEPLOY))
import launcher


class Win7LauncherTests(unittest.TestCase):
    def test_check_port_returns_zero_when_port_is_not_listening(self):
        result = subprocess.run(
            [sys.executable, str(LAUNCHER), "check-port", "--port", "19196"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_start_command_builds_package_environment_and_writable_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            runtime = package_root / "runtime"
            server = package_root / "KmMpsMcpServer"
            runtime.mkdir(parents=True)
            server.mkdir()
            python_exe = runtime / "python.exe"
            node_exe = runtime / "node.exe"
            agent_script = server / "agent_server.py"
            for path in (python_exe, node_exe, agent_script):
                path.write_text("fixture", encoding="utf-8")
            state_dir = Path(temp_dir) / "state"
            args = launcher.build_start_command(package_root, 9095, state_dir)
            self.assertEqual(str(python_exe), args[0])
            self.assertIn("-B", args[1:args.index(str(agent_script))])
            self.assertIn("--port", args)
            env = launcher.build_runtime_environment(package_root, state_dir)
            self.assertEqual("1", env["KMAI_WIN7_COMPAT"])
            self.assertEqual(str(python_exe), env["KMAI_PYTHON_EXE"])
            self.assertEqual(str(python_exe), env["KMAI_SKILL_PYTHON"])
            self.assertEqual(str(node_exe), env["KMAI_NODE_EXE"])
            self.assertEqual(str(state_dir), env["KMAI_RUNTIME_DIR"])
            self.assertEqual("1", env["PYTHONUTF8"])

    def test_health_requires_the_local_kmai_startup_identity(self):
        for payload, expected in (
            ({"status": "ok", "app": "KmAI", "kind": "agent"}, True),
            ({"status": "ok"}, False),
            ({"status": "ok", "app": "Other", "kind": "agent"}, False),
            ([], False),
        ):
            with self.subTest(payload=payload):
                response = mock.Mock(status=200)
                response.read.return_value = json.dumps(payload).encode("utf-8")
                with mock.patch.object(launcher, "urlopen", return_value=response) as request:
                    self.assertEqual(expected, launcher.health("127.0.0.1", 19095))
                self.assertEqual("http://127.0.0.1:19095/api/startup-ping", request.call_args.args[0])

    def test_state_directory_must_be_external_and_environment_must_be_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            package_root.mkdir()
            with self.assertRaises(launcher.LauncherError):
                launcher.ensure_external_state_dir(package_root / "runtime-state", package_root)
            with mock.patch.dict(
                os.environ,
                {
                    "KMAI_RUNTIME_DIR": "",
                    "LOCALAPPDATA": "",
                    "TEMP": "",
                    "TMP": "",
                    "USERPROFILE": "",
                },
                clear=False,
            ):
                with self.assertRaises(launcher.LauncherError):
                    launcher.resolve_state_dir(package_root)

    def test_state_directory_falls_back_to_temp_when_local_app_data_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(
                os.environ,
                {
                    "KMAI_RUNTIME_DIR": "",
                    "LOCALAPPDATA": "",
                    "TEMP": temp_dir,
                    "TMP": "",
                    "USERPROFILE": "",
                },
                clear=False,
            ):
                self.assertEqual(
                    (Path(temp_dir) / "KmAI").resolve(),
                    launcher.resolve_state_dir(),
                )

    def test_non_state_actions_do_not_require_runtime_directory(self):
        with mock.patch.dict(
            os.environ,
            {
                "KMAI_RUNTIME_DIR": "",
                "LOCALAPPDATA": "",
                "TEMP": "",
                "TMP": "",
                "USERPROFILE": "",
            },
            clear=False,
        ):
            self.assertEqual(0, launcher.main(["check-port", "--port", "19196"]))

    def test_occupied_healthy_port_is_not_accepted_without_exact_package_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            state_dir = Path(temp_dir) / "state"
            package_root.mkdir()
            state_dir.mkdir()
            state = {
                "pid": 1234,
                "port": 9095,
                "package_root": str(package_root),
                "agent_script": str(package_root / "KmMpsMcpServer" / "agent_server.py"),
            }
            with mock.patch.object(launcher, "check_port", return_value=1):
                with mock.patch.object(launcher, "read_state", return_value=state):
                    with mock.patch.object(launcher, "_state_process_matches", return_value=False):
                        with mock.patch.object(launcher, "health", return_value=True):
                            with self.assertRaises(launcher.LauncherError):
                                launcher.start(package_root, 9095, state_dir)

    def test_start_detaches_child_stdin_for_consoleless_win7_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            runtime = package_root / "runtime"
            server = package_root / "KmMpsMcpServer"
            runtime.mkdir(parents=True)
            server.mkdir()
            for path in (
                runtime / "python.exe",
                runtime / "node.exe",
                server / "agent_server.py",
            ):
                path.write_text("fixture", encoding="utf-8")
            state_dir = Path(temp_dir) / "state"
            process = mock.Mock(pid=1234)
            with mock.patch.object(launcher, "check_port", return_value=0):
                with mock.patch.object(launcher, "health", return_value=True):
                    with mock.patch.object(launcher.subprocess, "Popen", return_value=process) as popen:
                        self.assertEqual(0, launcher.start(package_root, 19095, state_dir))
            self.assertIs(popen.call_args.kwargs["stdin"], launcher.subprocess.DEVNULL)

    def test_state_process_matching_rejects_path_prefix_and_package_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="kmai package ") as temp_dir:
            package_root = Path(temp_dir) / "package"
            runtime = package_root / "runtime"
            server = package_root / "KmMpsMcpServer"
            runtime.mkdir(parents=True)
            server.mkdir()
            python_exe = runtime / "python.exe"
            agent_script = server / "agent_server.py"
            state = {
                "pid": 1234,
                "port": 9095,
                "agent_script": str(agent_script),
                "package_root": str(package_root),
            }
            exact = subprocess.list2cmdline([str(python_exe), str(agent_script), "--port", "9095"])
            spoofed = subprocess.list2cmdline([str(python_exe) + "-evil", str(agent_script), "--port", "9095"])
            with mock.patch.object(launcher, "query_process_commandline", return_value=(1234, exact)):
                self.assertTrue(launcher._state_process_matches(state, package_root, 9095))
                wrong_state = dict(state, package_root=str(package_root) + "-other")
                self.assertFalse(launcher._state_process_matches(wrong_state, package_root, 9095))
            with mock.patch.object(launcher, "query_process_commandline", return_value=(1234, spoofed)):
                self.assertFalse(launcher._state_process_matches(state, package_root, 9095))

    def test_stop_uses_wmic_and_taskkill_only_for_exact_matching_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            runtime = package_root / "runtime"
            server = package_root / "KmMpsMcpServer"
            runtime.mkdir(parents=True)
            server.mkdir()
            python_exe = runtime / "python.exe"
            agent_script = server / "agent_server.py"
            python_exe.write_text("fixture", encoding="utf-8")
            agent_script.write_text("fixture", encoding="utf-8")
            state = {
                "pid": 1234,
                "port": 9095,
                "agent_script": str(agent_script),
                "package_root": str(package_root),
            }
            with mock.patch.object(launcher, "query_process_commandline", return_value=(1234, str(python_exe) + " " + str(agent_script) + " --port 9095")):
                with mock.patch.object(launcher.subprocess, "run") as run:
                    run.return_value.returncode = 0
                    self.assertTrue(launcher.stop_state(state, package_root))
                    run.assert_called_once()
                    self.assertEqual(["taskkill", "/PID", "1234", "/T", "/F"], run.call_args[0][0])

    def test_stop_rejects_reused_pid_or_mismatched_command_without_kill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            runtime = package_root / "runtime"
            server = package_root / "KmMpsMcpServer"
            runtime.mkdir(parents=True)
            server.mkdir()
            python_exe = runtime / "python.exe"
            agent_script = server / "agent_server.py"
            python_exe.write_text("fixture", encoding="utf-8")
            agent_script.write_text("fixture", encoding="utf-8")
            state = {"pid": 1234, "port": 9095, "agent_script": str(agent_script), "package_root": str(package_root)}
            for commandline in ("other.exe --port 9095", str(python_exe) + " " + str(agent_script) + " --port 9096"):
                with self.subTest(commandline=commandline):
                    with mock.patch.object(launcher, "query_process_commandline", return_value=(1234, commandline)):
                        with mock.patch.object(launcher.subprocess, "run") as run:
                            self.assertFalse(launcher.stop_state(state, package_root))
                            run.assert_not_called()

    def test_stop_requires_integer_success_return_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "package"
            runtime = package_root / "runtime"
            server = package_root / "KmMpsMcpServer"
            runtime.mkdir(parents=True)
            server.mkdir()
            python_exe = runtime / "python.exe"
            agent_script = server / "agent_server.py"
            state = {
                "pid": 1234,
                "port": 9095,
                "agent_script": str(agent_script),
                "package_root": str(package_root),
            }
            commandline = subprocess.list2cmdline([str(python_exe), str(agent_script), "--port", "9095"])
            with mock.patch.object(launcher, "query_process_commandline", return_value=(1234, commandline)):
                with mock.patch.object(launcher.subprocess, "run") as run:
                    run.return_value.returncode = "0"
                    self.assertFalse(launcher.stop_state(state, package_root))

    def test_stop_rejects_cli_port_that_does_not_match_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            state_dir.mkdir()
            launcher.write_state(state_dir, {"pid": 1234, "port": 9095})
            with mock.patch.object(launcher, "stop_state") as stop_state:
                with self.assertRaises(launcher.LauncherError):
                    launcher.stop(Path(temp_dir) / "package", state_dir, 9096)
                stop_state.assert_not_called()

    def test_batch_wrappers_use_python_runtime_without_forbidden_commands(self):
        start = (DEPLOY / "start_win7.bat").read_text(encoding="utf-8")
        stop = (DEPLOY / "stop_win7.bat").read_text(encoding="utf-8")
        self.assertNotIn("Get-NetTCPConnection", start + stop)
        self.assertNotIn("Start-Process", start + stop)
        self.assertIn('set "PACKAGE_ROOT=%BASE_DIR:~0,-1%"', start + stop)
        self.assertIn('set "KMAI_NODE_EXE=%BASE_DIR%runtime\\node.exe"', start + stop)
        self.assertNotIn('runtime\\r\\node.exe', start + stop)
        self.assertIn('--package-root "%PACKAGE_ROOT%"', start + stop)
        self.assertIn('"%BASE_DIR%runtime\\python.exe" "%BASE_DIR%launcher.py" start', start)
        self.assertIn('"%BASE_DIR%runtime\\python.exe" "%BASE_DIR%launcher.py" stop', stop)

    def test_win7_batch_templates_use_crlf_line_endings(self):
        for name in ("start_win7.bat", "stop_win7.bat", "start_agent.bat", "stop_agent.bat"):
            raw = (DEPLOY / name).read_bytes()
            self.assertGreater(raw.count(b"\r\n"), 0, name)
            self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"), name)

    def test_legacy_agent_aliases_delegate_to_win7_launcher(self):
        root_start = (DEPLOY / "start_agent.bat").read_text(encoding="utf-8")
        root_stop = (DEPLOY / "stop_agent.bat").read_text(encoding="utf-8")
        self.assertIn('call "%BASE_DIR%start_win7.bat" %*', root_start)
        self.assertIn('call "%BASE_DIR%stop_win7.bat" %*', root_stop)

        source_start = (ROOT / "KmMpsMcpServer" / "start_agent.bat").read_text(encoding="utf-8")
        source_stop = (ROOT / "KmMpsMcpServer" / "stop_agent.bat").read_text(encoding="utf-8")
        self.assertIn('call "%BASE_DIR%..\\start_win7.bat" %*', source_start)
        self.assertIn('call "%BASE_DIR%..\\stop_win7.bat" %*', source_stop)
        self.assertNotIn('Get-NetTCPConnection', source_start + source_stop)
        self.assertNotIn('Start-Process', source_start + source_stop)


if __name__ == "__main__":
    unittest.main()
