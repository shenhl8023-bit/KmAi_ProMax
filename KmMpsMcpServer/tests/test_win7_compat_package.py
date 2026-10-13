# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[4] / "win7-compat"


class Win7CompatPackageTests(unittest.TestCase):
    def test_package_contains_x64_runtime_contract_and_safe_launchers(self):
        readme = (PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
        requirements = (PACKAGE_ROOT / "requirements-win7-x64.txt").read_text(encoding="utf-8")
        start = (PACKAGE_ROOT / "start_win7.bat").read_text(encoding="utf-8")
        stop = (PACKAGE_ROOT / "stop_win7.bat").read_text(encoding="utf-8")
        launcher = (PACKAGE_ROOT / "launcher.py").read_text(encoding="utf-8")

        self.assertIn("Windows 7 SP1 x64", readme)
        self.assertIn("Python 3.8", requirements)
        self.assertNotIn("Get-NetTCPConnection", start + stop)
        self.assertNotIn("Start-Process", start + stop)
        self.assertIn("runtime\\python.exe", start)
        self.assertIn("taskkill", launcher.lower())

    def test_build_manifest_forbids_machine_config_and_secrets(self):
        manifest = json.loads((PACKAGE_ROOT / "package-manifest.json").read_text(encoding="utf-8"))
        excluded = set(manifest["exclude"])
        self.assertIn("config.ini", excluded)
        self.assertIn("__pycache__", excluded)
        self.assertIn("*.pyc", excluded)
        self.assertNotIn("api_key", json.dumps(manifest).lower())

    def test_win7_config_uses_relative_prebuilt_model_directory(self):
        config = (PACKAGE_ROOT / "config.example.ini").read_text(encoding="utf-8")
        self.assertIn("win7_lite_mode = true", config)
        self.assertIn("prebuilt_model_dir = ..\\models", config)
        self.assertNotIn("/Users/", config)
        self.assertNotIn("C:\\Users\\", config)

    def test_launcher_check_port_action_is_executable(self):
        result = subprocess.run(
            [sys.executable, str(PACKAGE_ROOT / "launcher.py"), "check-port", "--port", "19196"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
