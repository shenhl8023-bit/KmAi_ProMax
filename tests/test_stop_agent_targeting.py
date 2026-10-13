# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import re
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_ROOT = os.path.join(ROOT, "KmMpsMcpServer")


class StopAgentTargetingTests(unittest.TestCase):
    def test_stop_script_filters_agent_processes_by_port_and_base_dir(self):
        script_path = os.path.join(SERVER_ROOT, "stop_agent.bat")
        with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            script = fp.read()

        self.assertIn("BASE_DIR=%~dp0", script)
        self.assertIn("--port", script)
        self.assertIn("$targetPortArg", script)
        self.assertIn("$targetScript", script)
        self.assertIn("[IO.Path]::GetFullPath", script)

        process_filter = re.search(
            r"\$procs\s*=\s*Get-CimInstance Win32_Process \| Where-Object \{(?P<body>.*?)\};",
            script,
            re.DOTALL,
        )
        self.assertIsNotNone(process_filter)
        body = process_filter.group("body")
        self.assertIn("agent_server.py", body)
        self.assertIn("$targetScript", body)
        self.assertIn("$targetPortArg", body)
        self.assertNotIn("-like '*agent_server.py*' }", body)

    def test_stop_script_does_not_force_stop_every_agent_server_process(self):
        script_path = os.path.join(SERVER_ROOT, "stop_agent.bat")
        with open(script_path, "r", encoding="utf-8-sig", errors="replace") as fp:
            script = fp.read()

        self.assertNotIn(
            "$_.CommandLine -like '*agent_server.py*' };",
            script,
        )
        self.assertIn("No matching agent_server.py process found", script)


if __name__ == "__main__":
    unittest.main()
