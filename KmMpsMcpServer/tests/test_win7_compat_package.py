# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "deploy" / "win7-compat"


class Win7CompatPackageTests(unittest.TestCase):
    def test_package_contains_x64_runtime_contract_and_safe_launchers(self):
        readme = (PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
        requirements = (PACKAGE_ROOT / "requirements-win7-x64.txt").read_text(encoding="utf-8")
        start = (PACKAGE_ROOT / "start_win7.bat").read_text(encoding="utf-8")
        stop = (PACKAGE_ROOT / "stop_win7.bat").read_text(encoding="utf-8")
        legacy_start = (PACKAGE_ROOT / "start_agent.bat").read_text(encoding="utf-8")
        legacy_stop = (PACKAGE_ROOT / "stop_agent.bat").read_text(encoding="utf-8")
        launcher = (PACKAGE_ROOT / "launcher.py").read_text(encoding="utf-8")

        self.assertIn("Windows 7 SP1 x64", readme)
        self.assertIn("Python 3.8", requirements)
        self.assertNotIn("Get-NetTCPConnection", start + stop)
        self.assertNotIn("Start-Process", start + stop)
        self.assertIn("runtime\\python.exe", start)
        self.assertIn("%TEMP%\\KmAI", start + stop)
        self.assertIn("%USERPROFILE%\\AppData\\Local\\KmAI", start + stop)
        self.assertIn("start_win7.bat", legacy_start)
        self.assertIn("stop_win7.bat", legacy_stop)
        self.assertIn("taskkill", launcher.lower())

    def test_build_manifest_forbids_machine_config_and_secrets(self):
        manifest = json.loads((PACKAGE_ROOT / "package-manifest.json").read_text(encoding="utf-8"))
        excluded = set(manifest["exclude"])
        self.assertIn("config.ini", excluded)
        self.assertIn("__pycache__", excluded)
        self.assertIn("*.pyc", excluded)
        self.assertNotIn("api_key", json.dumps(manifest).lower())

    def test_win7_config_uses_realtime_step_conversion_by_default(self):
        config = (PACKAGE_ROOT / "config.example.ini").read_text(encoding="utf-8")
        self.assertIn("enabled = false", config)
        self.assertIn("win7_lite_mode = false", config)
        self.assertIn("step_viewer_root = step-compare", config)
        self.assertIn("prebuilt_model_dir =", config)
        self.assertIn("matching_backend = feature_vector", config)
        self.assertIn("feature_api_base_url =", config)
        self.assertIn("feature_model_version =", config)
        self.assertIn("xml_library_dir = Resources/SimilarParts/XML样本", config)
        self.assertIn("current_part_dir =", config)
        self.assertIn("current_xml_file = C:/tmp/3dmps-data/AIBasicInfo.xml", config)
        self.assertIn("current_step_file = C:/tmp/3dmps-data/stepModel.stp", config)
        self.assertIn("# 配置获批的内部特征服务地址和模型版本后，再将此项设为 true。", config)
        self.assertNotIn("# Set true after configuring", config)
        self.assertNotIn("# Win7 keeps the STEP path live", config)
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
